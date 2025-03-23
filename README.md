# FastAPI Social Media Backend

A robust social media backend built with FastAPI, featuring a modern NoSQL-focused architecture for optimal performance and scalability. The system supports advanced content management, semantic search, engagement tracking, and content classification.

> **Note: We are currently in the process of transitioning to a fully NoSQL approach. Some parts of the codebase are under construction as we migrate from our previous hybrid database architecture.**

## 🏗️ Architecture

### Databases
- **MongoDB**: Primary database for core data, relationships, document storage, and caching
- **Qdrant**: Vector database for semantic search

### Tech Stack
- Python 3.10+
- FastAPI
- Motor (MongoDB async driver)
- Sentence Transformers
- Pydantic

## 🚀 Features

### Post Management
- CRUD operations for posts
- Media handling support
- Content validation
- Metadata management

### Threading System
- Twitter-style thread creation
- Dynamic thread expansion
- Position management
- Thread status tracking

### Content Classification
- Hashtag management
- @mention system
- Topic classification
- Trending analysis

### Search Capabilities
- Semantic search using embeddings
- Traditional text search
- Advanced filtering
- Search suggestions

### Engagement Tracking
- Like system
- View counting
- User interaction history
- Engagement metrics

## 🛠️ Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/fastapi-social-backend.git
cd fastapi-social-backend
```

2. **Create and activate virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Unix
venv\Scripts\activate     # Windows
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up databases**
```bash
# MongoDB
docker run -d --name mongodb -p 27017:27017 mongo

# Qdrant
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant


```

5. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your configuration
```

## ⚙️ Configuration

```python
# app/core/config.py
class Settings:
    PROJECT_NAME: str = "Social Media Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "social_media"
    
    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    

```

## 🗄️ Project Structure

```
app/
├── alembic.ini
├── migrations/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   └── endpoints/
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── auth.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── models.py
│   │   ├── mongodb.py
│   │   └── qdrant.py
│   ├── follow/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   ├── posts/
│   │   ├── __init__.py
│   │   ├── routers/
│   │   │   ├── core.py
│   │   │   ├── threads.py
│   │   │   ├── search.py
│   │   │   ├── classification.py
│   │   │   ├── user_content.py
│   │   │   ├── engagement.py
│   │   │   └── hashtag.py
│   │   ├── schemas/
│   │   │   ├── thread_schemas.py
│   │   │   ├── search_schemas.py
│   │   │   └── post_response.py
│   │   ├── services/
│   │   │   ├── core_post_service.py
│   │   │   ├── thread_service.py
│   │   │   ├── comprehensive_search_service.py
│   │   │   ├── batched_search_service.py
│   │   │   ├── embedding_service.py
│   │   │   ├── engagement_service.py
│   │   │   ├── content_classification_service.py
│   │   │   └── hashtag_service.py
│   │   └── router.py
│   ├── profile/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   └── settings/
│       ├── __init__.py
│       ├── models.py
│       ├── router.py
│       ├── schemas.py
│       └── service.py
├── ml/
│   └── ...
├── tests/
│   └── __init__.py
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

## 🚦 API Endpoints

### Posts
- `POST   /api/posts/`              Create post
- `GET    /api/posts/{post_id}`     Get post
- `PUT    /api/posts/{post_id}`     Update post
- `DELETE /api/posts/{post_id}`     Delete post
- `GET    /api/posts/`              List posts

### Threads
- `POST   /api/threads/`            Create thread
- `GET    /api/threads/{id}`        Get thread
- `PUT    /api/threads/{id}`        Update thread
- `POST   /api/threads/{id}/posts`  Add to thread

### Search
- `GET    /api/search/posts`        Search posts
- `GET    /api/search/suggest`      Get suggestions

### Engagement
- `POST   /api/posts/{id}/like`     Toggle like
- `GET    /api/posts/{id}/stats`    Get engagement stats

## 🧪 Testing

Run tests using pytest:

```bash
pytest
```

## 📈 Performance Considerations

- Efficient NoSQL data modeling
- Denormalization strategies for read-heavy operations
- MongoDB caching capabilities
- Batch processing for embeddings
- Asynchronous operations
- Connection pooling
- Optimized document design for frequent queries

## 🛡️ Security

- Authentication required for protected endpoints
- Input validation
- Rate limiting preparation
- NoSQL injection prevention
- XSS protection

## 🔄 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Acknowledgments

- FastAPI for the amazing framework
- MongoDB for flexible document storage
- Sentence Transformers for embedding generation
- Qdrant for vector similarity search
- MongoDB for flexible document storage and caching

## 📞 Contact

For questions and support, please open an issue or contact the maintainers.
