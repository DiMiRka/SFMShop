from fastapi import APIRouter, Query, status

from sfmshop.core.dependencies import current_user, review_read_service, review_write_service
from sfmshop.schemas.reviews import ReviewCreate, ReviewList, ReviewResponse, ReviewUpdate

reviews_router = APIRouter(tags=["reviews"])


@reviews_router.get("/products/{product_id}/reviews", summary="Отзывы о товаре",
                    response_model=ReviewList, status_code=status.HTTP_200_OK)
async def get_reviews(service: review_read_service, product_id: int,
                      limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await service.list_reviews(product_id, limit, offset)


@reviews_router.post("/products/{product_id}/reviews", summary="Оставить отзыв на купленный товар",
                     response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def post_review(cu: current_user, service: review_write_service, product_id: int, review: ReviewCreate):
    return await service.create_review(cu, product_id, review)


@reviews_router.patch("/reviews/{review_id}", summary="Изменить свой отзыв",
                      response_model=ReviewResponse, status_code=status.HTTP_200_OK)
async def patch_review(cu: current_user, service: review_write_service, review_id: int, review: ReviewUpdate):
    return await service.update_review(cu, review_id, review)


@reviews_router.delete("/reviews/{review_id}", summary="Удалить отзыв: свой или любой для админа",
                       status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(cu: current_user, service: review_write_service, review_id: int):
    await service.delete_review(cu, review_id)
