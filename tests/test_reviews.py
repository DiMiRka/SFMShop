from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from src.api.main import sfmshop_app as app
from src.core import dependencies
from src.database.models import Review
from src.models.exceptions import BusinessLogicError, ForbiddenError, NotFoundError
from src.repositories.order_repository import OrderRepository
from src.repositories.product_repository import ProductRepository
from src.repositories.review_repository import ReviewRepository
from src.schemas.reviews import ReviewCreate, ReviewUpdate
from src.services.product_service import ProductService
from src.services.review_service import ReviewService
from tests.test_queue import FakeMessage, build_consumer
from tests.test_services import FakeCache, FakeDb, FakeQueue, OrderRepoFake, ProductRepoFake


pytestmark = pytest.mark.anyio

BUYER = SimpleNamespace(id=1, is_admin=False)
STRANGER = SimpleNamespace(id=2, is_admin=False)
ADMIN = SimpleNamespace(id=9, is_admin=True)


class ReviewRepoFake:
    def __init__(self):
        self.db = FakeDb()
        self.reviews = {}
        self.create_error = None

    def add_review(self, review_id=5, user_id=1, product_id=1, rating=4, text="Хорошая мышь"):
        review = Review(product_id=product_id, user_id=user_id, rating=rating, text=text)
        review.id = review_id
        review.created_at = datetime(2026, 1, 1)
        self.reviews[review_id] = review
        return review

    async def get_by_product(self, product_id, limit=20, offset=0):
        self.page = (limit, offset)
        return [r for r in self.reviews.values() if r.product_id == product_id]

    async def get_by_id_for_update(self, review_id):
        return self.reviews.get(review_id)

    async def get_by_product_and_user(self, product_id, user_id):
        return next((r for r in self.reviews.values() if (r.product_id, r.user_id) == (product_id, user_id)), None)

    async def create(self, data):
        if self.create_error:
            raise self.create_error
        return self.add_review(review_id=len(self.reviews) + 100, **data)

    async def update(self, review, data):
        for field, value in data.items():
            setattr(review, field, value)

    async def delete(self, review):
        del self.reviews[review.id]


def make_service():
    reviews, queue = ReviewRepoFake(), FakeQueue()
    service = ReviewService(reviews, ProductRepoFake(), OrderRepoFake(), queue)
    return service, reviews, queue


async def test_buyer_leaves_review_and_event_is_published():
    service, reviews, queue = make_service()

    created = await service.create_review(BUYER, 1, ReviewCreate(rating=5, text="  Отличная мышь  "))

    assert created["rating"] == 5 and created["text"] == "Отличная мышь"
    assert created["user_id"] == 1 and created["product_id"] == 1
    assert queue.events == [("product_exchange", "review.created",
                             {"review_ids": created["id"], "product_ids": 1, "user_ids": 1})]


async def test_only_buyer_can_review_product():
    service, reviews, queue = make_service()

    with pytest.raises(ForbiddenError):
        await service.create_review(STRANGER, 1, ReviewCreate(rating=5, text="Не покупал"))

    assert reviews.reviews == {} and queue.events == []


async def test_second_review_on_same_product_is_rejected():
    service, reviews, queue = make_service()
    reviews.add_review(user_id=1, product_id=1)

    with pytest.raises(BusinessLogicError):
        await service.create_review(BUYER, 1, ReviewCreate(rating=1, text="Ещё раз"))

    assert queue.events == []


async def test_concurrent_duplicate_hits_unique_constraint_and_becomes_conflict():
    service, reviews, queue = make_service()
    reviews.create_error = IntegrityError(
        "INSERT", {}, Exception('duplicate key value violates unique constraint "uq_reviews_product_user"'))

    with pytest.raises(BusinessLogicError):
        await service.create_review(BUYER, 1, ReviewCreate(rating=5, text="Гонка"))

    reviews.create_error = IntegrityError("INSERT", {}, Exception('violates foreign key constraint "fk_product"'))
    with pytest.raises(IntegrityError):
        await service.create_review(BUYER, 1, ReviewCreate(rating=5, text="Товар удалили"))
    assert queue.events == []


async def test_missing_product_is_not_found():
    service, _, _ = make_service()

    with pytest.raises(NotFoundError):
        await service.create_review(BUYER, 999, ReviewCreate(rating=5, text="Нет товара"))
    with pytest.raises(NotFoundError):
        await service.list_reviews(999, 20, 0)


async def test_list_returns_reviews_with_rating_summary():
    service, reviews, _ = make_service()
    reviews.add_review(review_id=5, rating=4)
    service.product_rep.rating = (4.0, 1)

    result = await service.list_reviews(1, 10, 0)

    assert result["average_rating"] == 4.0 and result["reviews_count"] == 1
    assert [r["id"] for r in result["reviews"]] == [5]
    assert reviews.page == (10, 0)


async def test_only_author_can_edit_review_even_admin_cannot():
    service, reviews, queue = make_service()
    reviews.add_review(review_id=5, user_id=1)

    for user in (STRANGER, ADMIN):
        with pytest.raises(ForbiddenError):
            await service.update_review(user, 5, ReviewUpdate(rating=1))
    assert reviews.reviews[5].rating == 4 and queue.events == []

    updated = await service.update_review(BUYER, 5, ReviewUpdate(rating=2))
    assert updated["rating"] == 2 and updated["text"] == "Хорошая мышь"
    assert queue.events[-1][1] == "review.updated"

    with pytest.raises(NotFoundError):
        await service.update_review(BUYER, 404, ReviewUpdate(rating=2))


@pytest.mark.parametrize("user, allowed", [(BUYER, True), (ADMIN, True), (STRANGER, False)])
async def test_review_is_deleted_by_author_or_admin(user, allowed):
    service, reviews, queue = make_service()
    reviews.add_review(review_id=5, user_id=1)

    if allowed:
        await service.delete_review(user, 5)
        assert 5 not in reviews.reviews
        assert queue.events == [("product_exchange", "review.deleted",
                                 {"review_ids": 5, "product_ids": 1, "user_ids": 1})]
    else:
        with pytest.raises(ForbiddenError):
            await service.delete_review(user, 5)
        assert 5 in reviews.reviews and queue.events == []


async def test_product_card_shows_rating_and_review_event_resets_its_cache():
    products = ProductRepoFake()
    products.rating = (4.5, 2)

    card = await ProductService(products, FakeCache(), FakeQueue()).get_product_by_id(1)
    assert card["average_rating"] == 4.5 and card["reviews_count"] == 2

    service, reviews, queue = make_service()
    await service.create_review(BUYER, 1, ReviewCreate(rating=5, text="Супер"))
    consumer, cache = build_consumer()
    _, routing_key, payload = queue.events[-1]

    await consumer.process_cache_event(FakeMessage(routing_key, payload))

    cache.delete_products.assert_awaited_once_with(1)


@pytest.mark.parametrize("data", [
    {"rating": 0, "text": "x"},
    {"rating": 6, "text": "x"},
    {"rating": 5, "text": "   "},
    {"rating": 5, "text": "x" * 2001},
])
def test_review_create_validation(data):
    with pytest.raises(PydanticValidationError):
        ReviewCreate.model_validate(data)


def test_review_update_rejects_nulls():
    with pytest.raises(PydanticValidationError):
        ReviewUpdate.model_validate({"rating": None})


def test_review_table_constraints():
    constraints = {c.name: c for c in [*Review.__table__.constraints, *Review.__table__.c.rating.constraints]}

    assert set(constraints["uq_reviews_product_user"].columns.keys()) == {"product_id", "user_id"}
    assert str(constraints["check_review_rating"].sqltext) == "rating >= 1 AND rating <= 5"


class QueryDb:
    def __init__(self, result):
        self.result = result

    async def execute(self, query):
        self.sql = str(query.compile(dialect=postgresql.dialect()))
        return self.result


async def test_rating_purchase_and_listing_queries():
    rating_db = QueryDb(SimpleNamespace(one=lambda: (Decimal("4.333333"), 3)))
    assert await ProductRepository(rating_db).get_rating(1) == (4.33, 3)
    assert "avg(reviews.rating)" in rating_db.sql and "count(reviews.id)" in rating_db.sql

    empty_db = QueryDb(SimpleNamespace(one=lambda: (None, 0)))
    assert await ProductRepository(empty_db).get_rating(1) == (None, 0)

    purchase_db = QueryDb(SimpleNamespace(scalar_one_or_none=lambda: 10))
    assert await OrderRepository(purchase_db).has_purchased(1, 2) is True
    assert "JOIN orders" in purchase_db.sql
    assert "orders.user_id =" in purchase_db.sql and "order_items.product_id =" in purchase_db.sql

    list_db = QueryDb(SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])))
    assert await ReviewRepository(list_db).get_by_product(1, 10, 20) == []
    assert "ORDER BY reviews.created_at DESC, reviews.id DESC" in list_db.sql


client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def use_reviews(service, user=None):
    app.dependency_overrides[dependencies.get_review_read_service] = lambda: service
    app.dependency_overrides[dependencies.get_review_write_service] = lambda: service
    if user is not None:
        async def current_user():
            return user
        app.dependency_overrides[dependencies.get_current_user] = current_user


def review_service_mock():
    review = {"id": 5, "product_id": 1, "user_id": 1, "rating": 5, "text": "ok", "created_at": "2026-01-01T00:00:00"}
    return SimpleNamespace(
        list_reviews=AsyncMock(return_value={"product_id": 1, "average_rating": 5.0, "reviews_count": 1,
                                             "limit": 20, "offset": 0, "reviews": [review]}),
        create_review=AsyncMock(return_value=review),
        update_review=AsyncMock(return_value=review),
        delete_review=AsyncMock(return_value=None),
    )


def test_reviews_are_public_but_writing_needs_token():
    service = review_service_mock()
    use_reviews(service)

    assert client.get("/v1/products/1/reviews").status_code == 200
    service.list_reviews.assert_awaited_once_with(1, 20, 0)
    assert client.post("/v1/products/1/reviews", json={"rating": 5, "text": "ok"}).status_code == 401
    assert client.patch("/v1/reviews/5", json={"rating": 4}).status_code == 401
    assert client.delete("/v1/reviews/5").status_code == 401
    assert client.get("/v1/products/1/reviews", params={"limit": 1000}).status_code == 422


def test_review_routes_pass_current_user():
    service = review_service_mock()
    use_reviews(service, BUYER)

    assert client.post("/v1/products/1/reviews", json={"rating": 5, "text": "ok"}).status_code == 201
    assert service.create_review.await_args.args[:2] == (BUYER, 1)
    assert client.post("/v1/products/1/reviews", json={"rating": 9, "text": "ok"}).status_code == 422

    assert client.patch("/v1/reviews/5", json={"text": "новый"}).status_code == 200
    assert service.update_review.await_args.args[:2] == (BUYER, 5)

    assert client.delete("/v1/reviews/5").status_code == 204
    service.delete_review.assert_awaited_once_with(BUYER, 5)


async def test_review_repository_delegates_to_session():
    from tests.test_repositories_clients_api import ExecuteResult, RepoDb

    review = Review(product_id=1, user_id=1, rating=5, text="ok")
    db = RepoDb(ExecuteResult([review], review))
    repo = ReviewRepository(db)

    assert await repo.get_all() == [review]
    assert await repo.get_by_id(1) is review
    assert await repo.get_by_id_for_update(1) is review
    assert "FOR UPDATE" in str(db.query.compile(dialect=postgresql.dialect()))
    assert await repo.get_by_product_and_user(1, 1) is review

    created = await repo.create({"product_id": 2, "user_id": 1, "rating": 3, "text": "норм"})
    assert created.id == 123 and db.flushed
    await repo.update(review, {"rating": 1})
    assert review.rating == 1
    await repo.delete(review)
    assert db.deleted == [review]


async def test_deleting_missing_review_is_not_found():
    service, _, queue = make_service()

    with pytest.raises(NotFoundError):
        await service.delete_review(BUYER, 404)
    assert queue.events == []
