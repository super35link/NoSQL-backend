from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta

from app.db.models import Post, User, Hashtag, post_hashtags
from app.db.qdrant import QdrantManager
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
                    query, filters, min_score, limit, offset
                )
            elif search_type == "text":
                return await self._text_search(
                    session, query, filters, limit, offset
                )
            else:  # combined
                return await self._combined_search(
                    session, query, filters, min_score, limit, offset
                )
        except Exception as e:
            logger.error(f"Search error: {e}")
            raise

    async def _semantic_search(
        self,
        query: str,
        filters: Optional[Dict],
        min_score: float,
        limit: int,
        offset: int
    ) -> Dict:
        """Perform semantic search using Qdrant"""
        # Generate query embedding
        query_embedding = await self.embedding_service.generate_embedding(query)

        # Prepare Qdrant filters
        qdrant_filter = self._prepare_qdrant_filters(filters)

        # Search in Qdrant
        results = await self.qdrant.search(
            query_vector=query_embedding,
            query_filter=qdrant_filter,
            limit=limit + offset
        )

        # Process results
        posts = results[offset:offset + limit]
        return {
            "items": [
                {
                    "post_id": post["id"],
                    "content": post["payload"]["content"],
                    "author_id": post["payload"]["author_id"],
                    "created_at": post["payload"]["created_at"],
                    "score": post["score"],
                    "hashtags": post["payload"].get("hashtags", [])
                }
                for post in posts
            ],
            "total": len(results),
            "type": "semantic"
        }

    async def _text_search(
        self,
        session: AsyncSession,
        query: str,
        filters: Optional[Dict],
        limit: int,
        offset: int
    ) -> Dict:
        """Perform traditional text-based search"""
        # Build base query
        base_query = (
            select(Post)
            .join(User, Post.author_id == User.id)
            .outerjoin(post_hashtags)
            .outerjoin(Hashtag)
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

        # Get total count
        total = await session.scalar(
            select(func.count()).select_from(base_query.subquery())
        )

        # Get paginated results
        results = await session.execute(
            base_query
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        posts = results.unique().scalars().all()

        return {
            "items": [
                {
                    "post_id": post.id,
                    "content": post.content,
                    "author_id": post.author_id,
                    "created_at": post.created_at,
                    "hashtags": [tag.tag for tag in post.hashtags]
                }
                for post in posts
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
            query, filters, min_score, limit, 0
        )
        text_results = await self._text_search(
            session, query, filters, limit, 0
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
