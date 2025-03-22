from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import joinedload 
from typing import List, Dict, Optional
import logging

from app.db.models import Post, User, Hashtag, post_hashtags
from app.db.qdrant import QdrantManager
from app.posts.schemas.post_response import PostListResponse, create_post_response
from .embedding_service import PostEmbeddingService

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.embedding_service = PostEmbeddingService()
        self.qdrant = QdrantManager()

    async def search_posts(
        self,
        session: AsyncSession,
        query: str,
        search_type: str = "combined",
        filters: Optional[Dict] = None,
        min_score: float = 0.0,
        limit: int = 20,
        offset: int = 0
    ) -> Dict:
        """
        Comprehensive search functionality supporting different search types:
        - semantic: Vector-based semantic search
        - text: Traditional text-based search
        - combined: Combines both approaches
        """
        try:
            if search_type == "semantic":
                return await self._semantic_search(
                    session,  # Pass the session here
                    query, 
                    filters, 
                    min_score, 
                    limit, 
                    offset
                )
            elif search_type == "text":
                return await self._text_search(
                    session,
                    query,
                    filters,
                    limit,
                    offset
                )
            else:  # combined
                return await self._combined_search(
                    session,
                    query,
                    filters,
                    min_score,
                    limit,
                    offset
                )
        except Exception as e:
            logger.error(f"Search error: {e}")
            raise

    async def _semantic_search(
        self,
        session: AsyncSession,
        query: str,
        filters: Optional[Dict],
        min_score: float,
        limit: int,
        offset: int
    ) -> Dict:
        try:
            # Generate query embedding and search Qdrant
            query_embedding = await self.embedding_service.generate_embedding(query)
            qdrant_results = await self.qdrant.search_similar_posts(
                query_vector=query_embedding,
                filter_conditions=self._prepare_qdrant_filters(filters),
                limit=limit + offset,
                score_threshold=min_score
            )

            if not qdrant_results:
                return PostListResponse(
                    items=[],
                    total=0,
                    type="semantic",
                    has_more=False
                ).model_dump()

            # Get post IDs and scores
            post_ids = [int(result["post_id"]) for result in qdrant_results]
            scores_by_id = {int(result["post_id"]): result["score"] for result in qdrant_results}

            # Fetch posts with authors and engagement data
            posts_query = (
                select(Post, User)
                .join(User, Post.author_id == User.id)
                .where(Post.id.in_(post_ids))
                .options(
                    joinedload(Post.hashtags),
                    joinedload(Post.mentioned_users)
                )
            )
            
            result = await session.execute(posts_query)
            posts_with_authors = result.unique().all()

            # Fetch engagement data in bulk
            engagement_data = await self._fetch_bulk_engagement(
                session,
                [post.id for post, _ in posts_with_authors]
            )

            # Create unified responses
            post_responses = [
                create_post_response(
                    post=post,
                    user=user,
                    engagement_data=engagement_data.get(post.id),
                    search_score=scores_by_id.get(post.id)
                )
                for post, user in posts_with_authors
            ]

            # Sort by search score and apply pagination
            post_responses.sort(key=lambda x: x.score or 0, reverse=True)
            paginated_posts = post_responses[offset:offset + limit]

            return PostListResponse(
                items=paginated_posts,
                total=len(post_responses),
                type="semantic",
                has_more=len(paginated_posts) == limit
            ).model_dump()

        except Exception as e:
            logger.error(f"Error in semantic search: {str(e)}")
            raise

    async def _fetch_bulk_engagement(
        self,
        session: AsyncSession,
        post_ids: List[int]
    ) -> Dict[int, Dict]:
        """Fetch engagement data for multiple posts efficiently"""
        try:
            # This would integrate with your MongoDB service to fetch engagement data
            logger.debug(f"Fetching engagement data for post_ids: {post_ids}")

            engagement_data = await self.mongodb.post_engagements.find(
                {"post_id": {"$in": post_ids}}
            ).to_list(None)
            
            logger.debug(f"Raw engagement data from MongoDB: {engagement_data}")
            
            return {
                item["post_id"]: {
                    "likes": item.get("likes", []),
                    "views": item.get("view_count", 0),
                    "unique_viewers": len(item.get("viewers", [])),
                    "engagement_score": item.get("engagement_score", 0.0),
                    "is_liked": item.get("is_liked", False),
                    "last_updated": item.get("last_updated")
                }
                for item in engagement_data
            }
        except Exception as e:
            logger.error(f"Error fetching bulk engagement data: {e}")
            return {}


    async def _text_search(
        self,
        session: AsyncSession,
        query: str,
        filters: Optional[Dict],
        limit: int,
        offset: int
    ) -> Dict:
        """Perform traditional text-based search"""
        # Build base query with eager loading
        base_query = (
            select(Post, User.username)
            .join(User, Post.author_id == User.id)
            .outerjoin(post_hashtags)
            .outerjoin(Hashtag)
            .options(
                joinedload(Post.hashtags),        # Eagerly load hashtags
                joinedload(Post.mentioned_users)  # Eagerly load mentioned users
            )
        )

        # Add text search conditions
        search_terms = query.split()
        search_conditions = []
        for term in search_terms:
            search_conditions.append(
                or_(
                    Post.content.ilike(f"%{term}%"),
                    User.username.ilike(f"%{term}%"),
                    Hashtag.tag.ilike(f"%{term}%")
                )
            )
        
        if search_conditions:
            base_query = base_query.where(and_(*search_conditions))

        # Add filters
        if filters:
            base_query = self._apply_sql_filters(base_query, filters)

        # Get total count with a subquery
        count_query = select(func.count()).select_from(base_query.subquery())
        total = await session.scalar(count_query)

        # Get paginated results
        results = await session.execute(
            base_query
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        # Process results
        results = results.unique().all()
        posts_with_authors = [(post, username) for post, username in results]

        return {
            "items": [
                {
                    "post_id": post.id,
                    "content": post.content,
                    "author_id": post.author_id,
                    "author_username": username,
                    "created_at": post.created_at,
                    "like_count": post.like_count or 0,
                    "view_count": post.view_count or 0,
                    "repost_count": post.repost_count or 0,
                    "hashtags": [tag.tag for tag in post.hashtags] if post.hashtags else [],
                    "mentioned_usernames": [user.username for user in post.mentioned_users] if post.mentioned_users else []
                }
                for post, username in posts_with_authors
            ],
            "total": total,
            "type": "text"
        }

    async def _combined_search(
        self,
        session: AsyncSession,
        query: str,
        filters: Optional[Dict],
        min_score: float,
        limit: int,
        offset: int
    ) -> Dict:
        """Combine semantic and text search results"""
        # Perform both searches
        semantic_results = await self._semantic_search(
            session,  # Pass the session here
            query, 
            filters, 
            min_score, 
            limit, 
            0
        )
        text_results = await self._text_search(
            session,
            query,
            filters,
            limit,
            0
        )

        # Combine and deduplicate results
        combined = {}
        for post in semantic_results["items"]:
            post["search_type"] = "semantic"
            combined[post["post_id"]] = post

        for post in text_results["items"]:
            if post["post_id"] not in combined:
                post["search_type"] = "text"
                combined[post["post_id"]] = post

        # Sort by relevance/date
        sorted_results = sorted(
            combined.values(),
            key=lambda x: (
                x.get("score", 0) if x["search_type"] == "semantic" else 0,
                x["created_at"]
            ),
            reverse=True
        )

        return {
            "items": sorted_results[offset:offset + limit],
            "total": len(combined),
            "type": "combined"
        }

    async def suggest_search_terms(
        self,
        session: AsyncSession,
        partial_query: str,
        limit: int = 5
    ) -> List[str]:
        """Suggest search terms based on partial input"""
        if len(partial_query) < 2:
            return []

        # Search in hashtags
        hashtag_results = await session.execute(
            select(Hashtag.tag)
            .where(Hashtag.tag.ilike(f"{partial_query}%"))
            .limit(limit)
        )
        suggestions = [result[0] for result in hashtag_results]

        # Search in usernames
        if len(suggestions) < limit:
            username_results = await session.execute(
                select(User.username)
                .where(User.username.ilike(f"{partial_query}%"))
                .limit(limit - len(suggestions))
            )
            suggestions.extend([result[0] for result in username_results])

        return suggestions

    async def get_search_trends(
        self,
        session: AsyncSession,
        timeframe: str = "24h"
    ) -> List[Dict]:
        """Get trending search terms"""
        # This would typically integrate with your analytics service
        # Placeholder for now
        pass

    def _prepare_qdrant_filters(self, filters: Optional[Dict]) -> Optional[Dict]:
        """Convert generic filters to Qdrant-specific format"""
        if not filters:
            return None

        qdrant_filter = {"must": []}

        if "author_id" in filters:
            qdrant_filter["must"].append({
                "key": "author_id",
                "match": {"value": filters["author_id"]}
            })

        if "date_range" in filters:
            date_range = filters["date_range"]
            if "start" in date_range:
                qdrant_filter["must"].append({
                    "key": "created_at",
                    "range": {"gte": date_range["start"].isoformat()}
                })
            if "end" in date_range:
                qdrant_filter["must"].append({
                    "key": "created_at",
                    "range": {"lte": date_range["end"].isoformat()}
                })

        if "hashtags" in filters:
            qdrant_filter["must"].append({
                "key": "hashtags",
                "match": {"any": filters["hashtags"]}
            })

        return qdrant_filter if qdrant_filter["must"] else None

    def _apply_sql_filters(self, query, filters: Dict):
        """Apply filters to SQL query"""
        if "author_id" in filters:
            query = query.where(Post.author_id == filters["author_id"])

        if "date_range" in filters:
            date_range = filters["date_range"]
            if "start" in date_range:
                query = query.where(Post.created_at >= date_range["start"])
            if "end" in date_range:
                query = query.where(Post.created_at <= date_range["end"])

        if "hashtags" in filters:
            query = query.where(Hashtag.tag.in_(filters["hashtags"]))

        return query
