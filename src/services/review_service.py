from loguru import logger
from sqlalchemy.exc import IntegrityError

from src.core.permissions import ensure_owner, ensure_self_or_admin
from src.database.models import User
from src.core.exceptions import BusinessLogicError, ForbiddenError, NotFoundError
from src.repositories import OrderRepository, ProductRepository, ReviewRepository
from src.schemas.reviews import ReviewCreate, ReviewList, ReviewResponse, ReviewUpdate
from src.services.queue_producer import QueueProducer


class ReviewService:
    def __init__(
            self,
            review_rep: ReviewRepository,
            product_rep: ProductRepository,
            order_rep: OrderRepository,
            queue: QueueProducer):
        self.review_rep = review_rep
        self.product_rep = product_rep
        self.order_rep = order_rep
        self.queue = queue

    async def list_reviews(self, product_id: int, limit: int, offset: int) -> dict:
        if not await self.product_rep.get_by_id(product_id):
            raise NotFoundError("Товар не найден")

        reviews = await self.review_rep.get_by_product(product_id, limit, offset)
        average_rating, reviews_count = await self.product_rep.get_rating(product_id)

        return ReviewList(
            product_id=product_id,
            average_rating=average_rating,
            reviews_count=reviews_count,
            limit=limit,
            offset=offset,
            reviews=[ReviewResponse.model_validate(review) for review in reviews],
        ).model_dump(mode="json")

    async def create_review(self, user: User, product_id: int, review: ReviewCreate) -> dict:
        try:
            async with self.review_rep.db.begin():
                if not await self.product_rep.get_by_id(product_id):
                    raise NotFoundError("Товар не найден")

                if not await self.order_rep.has_purchased(user.id, product_id):
                    raise ForbiddenError("Отзыв можно оставить только на купленный товар")

                if await self.review_rep.get_by_product_and_user(product_id, user.id):
                    raise BusinessLogicError("Вы уже оставили отзыв на этот товар")

                review_db = await self.review_rep.create(
                    {"product_id": product_id, "user_id": user.id, **review.model_dump()}
                )
        except IntegrityError as exc:
            if "uq_reviews_product_user" not in str(exc.orig):
                raise
            logger.warning(f"Duplicate review user id={user.id} product id={product_id}")
            raise BusinessLogicError("Вы уже оставили отзыв на этот товар")

        await self._publish("review.created", review_db.id, product_id, user.id)
        return ReviewResponse.model_validate(review_db).model_dump(mode="json")

    async def update_review(self, user: User, review_id: int, review_update: ReviewUpdate) -> dict:
        async with self.review_rep.db.begin():
            review_db = await self.review_rep.get_by_id_for_update(review_id)

            if not review_db:
                raise NotFoundError("Отзыв не найден")

            ensure_owner(user, review_db.user_id)
            await self.review_rep.update(review_db, review_update.model_dump(exclude_unset=True))

        await self._publish("review.updated", review_id, review_db.product_id, review_db.user_id)
        return ReviewResponse.model_validate(review_db).model_dump(mode="json")

    async def delete_review(self, user: User, review_id: int) -> None:
        async with self.review_rep.db.begin():
            review_db = await self.review_rep.get_by_id_for_update(review_id)

            if not review_db:
                raise NotFoundError("Отзыв не найден")

            ensure_self_or_admin(user, review_db.user_id)
            product_id, author_id = review_db.product_id, review_db.user_id
            await self.review_rep.delete(review_db)

        await self._publish("review.deleted", review_id, product_id, author_id)

    async def _publish(self, routing_key: str, review_id: int, product_id: int, user_id: int) -> None:
        await self.queue.publish_event(
            "product_exchange",
            routing_key,
            {"review_ids": review_id, "product_ids": product_id, "user_ids": user_id},
        )

