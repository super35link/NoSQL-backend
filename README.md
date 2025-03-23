# FastAPI Social Media Backend

A robust social media backend built with FastAPI, featuring a modern NoSQL-focused architecture for optimal performance and scalability. The system supports advanced content management, semantic search, engagement tracking, and content classification.

> **IMPORTANT: PRIVATE REPOSITORY** - This is a private project. Access is restricted to developers specifically invited by the repository owner. All code and documentation are confidential.

> **Note: We are currently in the process of transitioning to a fully NoSQL approach. Some parts of the codebase are under construction as we migrate from our previous hybrid database architecture.**

## 🏗️ Architecture Overview

The project uses a modern, scalable architecture based on the following principles:
- Document-oriented data model
- Microservices-inspired organization
- Asynchronous processing
- Vector embeddings for semantic understanding
- Optimized MongoDB query patterns

### Databases
- **MongoDB**: Primary database for core data, relationships, document storage, and caching
- **Qdrant**: Vector database for semantic search

### Tech Stack
- **Backend Framework**: Python 3.10+ with FastAPI
- **Database Drivers**: Motor (MongoDB async driver)
- **ML Components**: Sentence Transformers for embeddings
- **Data Validation**: Pydantic for schema validation and data modeling
- **Authentication**: JWT-based auth with refresh tokens
- **Documentation**: OpenAPI (Swagger) auto-generation

## 🔧 Development Environment Setup

### Prerequisites
- Python 3.10+
- Docker and Docker Compose
- Git
- Poetry (optional but recommended)

### Initial Setup

1. **Clone the repository**
```bash
git clone https://github.com/super35link/fastapi-social-backend.git
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

4. **Set up databases with Docker**
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

### Running the Application

Development mode with auto-reload:
```bash
uvicorn app.main:app --reload
```

Production mode:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 📋 Developer Guidelines

### Code Style
- Follow PEP 8 guidelines
- Use type hints everywhere
- Document functions with docstrings
- Use async/await for I/O-bound operations

### Branching Strategy
- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/feature-name` - For new features
- `fix/bug-name` - For bug fixes

### Pull Request Process
1. Create feature/fix branch from `develop`
2. Implement changes with tests
3. Submit PR to `develop`
4. Code review required
5. After approval, squash and merge

### Testing
- Write unit tests for all new functionality
- Integration tests for critical paths
- Run tests before creating PRs

## 🚀 Core Features

### Post Management
- CRUD operations for posts
- Media handling support (images, videos)
- Content validation with customizable rules
- Metadata management
- Post scheduling
- Draft saving

### Threading System
- Twitter-style thread creation
- Dynamic thread expansion
- Position management with reordering support
- Thread status tracking
- Nested replies

### Content Classification
- Hashtag management with trending analytics
- @mention system with notification integration
- Topic classification using ML
- Custom taxonomies
- NSFW content detection

### Search Capabilities
- Semantic search using embeddings
- Traditional text search
- Advanced filtering (by date, author, engagement, etc.)
- Search suggestions and autocomplete
- Saved searches

### Engagement Tracking
- Like/react system with custom reactions
- View counting with duplicate detection
- User interaction history
- Engagement metrics and reporting
- Content performance analytics

### User and Profile Management
- Comprehensive user profiles
- Follow/following system
- Privacy settings
- Notification preferences
- Activity history

## ⚙️ Configuration

The application is configured using environment variables loaded from a `.env` file. Here's a sample configuration:

```python
# app/core/config.py
class Settings:
    PROJECT_NAME: str = "Social Media Backend"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Authentication
    SECRET_KEY: str = "your-secret-key"  # Change in production
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "social_media"
    
    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "post_embeddings"
    
    # Machine Learning
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    CONTENT_CLASSIFICATION_THRESHOLD: float = 0.7
```

## 🗄️ Project Structure

```
app/
├── alembic/
│   ├── versions/
│   │   └── c70b6d7261ba_initial.py
│   └── env.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── router.py
│   │   └── endpoints/
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── auth.py
│   │   ├── manager.py
│   │   └── apple/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── tasks/
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
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── embeddings.py
│   │   ├── classification.py
│   │   └── recommendation.py
│   ├── posts/
│   │   ├── __init__.py
│   │   ├── router.py
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
│   │   └── services/
│   │       ├── core_post_service.py
│   │       ├── thread_service.py
│   │       ├── comprehensive_search_service.py
│   │       ├── batched_search_service.py
│   │       ├── embedding_service.py
│   │       ├── engagement_service.py
│   │       ├── content_classification_service.py
│   │       └── hashtag_service.py
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
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_posts.py
│   └── integration/
│       └── test_end_to_end.py
├── scripts/
│   ├── seed_db.py
│   ├── generate_embeddings.py
│   └── performance_test.py
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── LICENSE
├── pyproject.toml
├── README.md
└── requirements.txt
```

## 🚦 API Endpoints Reference

### Authentication
- `POST   /api/auth/register`       Register new user
- `POST   /api/auth/login`          User login
- `POST   /api/auth/refresh`        Refresh access token
- `POST   /api/auth/logout`         User logout
- `GET    /api/auth/me`             Get current user

### Posts
- `POST   /api/posts/`              Create post
- `GET    /api/posts/{post_id}`     Get post by ID
- `PUT    /api/posts/{post_id}`     Update post
- `DELETE /api/posts/{post_id}`     Delete post
- `GET    /api/posts/`              List posts with pagination/filtering
- `POST   /api/posts/batch`         Create multiple posts

### Threads
- `POST   /api/threads/`            Create thread
- `GET    /api/threads/{id}`        Get thread
- `PUT    /api/threads/{id}`        Update thread
- `POST   /api/threads/{id}/posts`  Add to thread
- `GET    /api/threads/user/{id}`   Get user's threads

### Search
- `GET    /api/search/posts`        Search posts
- `GET    /api/search/suggest`      Get search suggestions
- `GET    /api/search/semantic`     Semantic similarity search
- `POST   /api/search/advanced`     Advanced multi-criteria search

### Engagement
- `POST   /api/posts/{id}/like`     Toggle like
- `GET    /api/posts/{id}/stats`    Get engagement stats
- `POST   /api/posts/{id}/view`     Record view
- `GET    /api/posts/trending`      Get trending posts

### Profile & Follow
- `GET    /api/profile/{id}`        Get user profile
- `PUT    /api/profile/`            Update profile
- `POST   /api/follow/{id}`         Follow user
- `DELETE /api/follow/{id}`         Unfollow user
- `GET    /api/follow/followers`    Get followers
- `GET    /api/follow/following`    Get following

### Settings
- `GET    /api/settings/`           Get user settings
- `PUT    /api/settings/`           Update settings
- `GET    /api/settings/privacy`    Get privacy settings
- `PUT    /api/settings/privacy`    Update privacy settings

## 📈 Performance Optimization

The application is designed with performance in mind, implementing several optimization strategies:

### MongoDB Optimizations
- Strategic indexing for common query patterns
- Denormalization where appropriate for read-heavy operations
- MongoDB caching capabilities with TTL indexes
- Aggregation pipeline optimizations
- Document design optimized for access patterns

### Query Optimizations
- Pagination for all list endpoints
- Projection to return only necessary fields
- Batch operations for bulk updates
- Cursor-based pagination for large datasets

### Processing Optimizations
- Asynchronous processing for I/O-bound operations
- Background tasks for long-running processes
- Batch processing for embeddings generation
- Connection pooling for database connections

### Caching Strategies
- In-memory caching for frequently accessed data
- MongoDB TTL collections for time-sensitive data
- Document-level caching with versioning
- Cache invalidation on updates

## 🛡️ Security Implementation

### Authentication & Authorization
- JWT-based authentication
- Role-based access control
- Refresh token rotation
- Token blacklisting

### Data Protection
- Input validation with Pydantic
- NoSQL injection prevention
- XSS protection
- CORS configuration

### Privacy
- Personal data minimization
- Data access controls
- Content visibility rules
- User consent tracking

## 📊 Monitoring and Logging

### Logging
- Structured logging with correlation IDs
- Log levels (DEBUG, INFO, WARNING, ERROR)
- Request/response logging
- Performance metric logging

### Monitoring
- Endpoint performance metrics
- Database query performance
- Error rate tracking
- Resource utilization monitoring

## 🧪 Testing Strategy

### Unit Testing
- Service-level tests
- Repository pattern tests
- Schema validation tests

### Integration Testing
- API endpoint tests
- Database interaction tests
- Authentication flow tests

### Performance Testing
- Load testing critical endpoints
- Database query performance
- Concurrency testing

Run tests using pytest:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_posts.py

# Run with coverage report
pytest --cov=app
```

## 🛠️ DevOps Integration

### CI/CD Pipeline
- GitHub Actions workflow
- Automated testing
- Linting and code quality checks
- Docker image building

### Deployment
- Containerized deployment with Docker
- Kubernetes configuration (optional)
- Environment-specific configurations
- Database migration handling

## 🔄 Contributing Guidelines

### Getting Started
1. Ensure you have been explicitly invited to this private repository
2. Clone the repository and set up your development environment
3. Review open issues and the project roadmap
4. Join the development Discord server for discussions

### Development Workflow
1. Fork the repository (if applicable)
2. Create a feature branch: `git checkout -b feature/feature-name`
3. Implement changes with tests
4. Follow the code style guidelines
5. Submit PR to `develop` branch
6. Address review comments
7. After approval, changes will be merged

### Code Review Process
- All code changes require review
- Maintainers will review PRs
- CI checks must pass
- Documentation must be updated

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributors & Acknowledgments

### Core Team
- Project Lead: super35link

### Acknowledgments
- FastAPI for the amazing framework
- MongoDB for flexible document storage and caching
- Sentence Transformers for embedding generation
- Qdrant for vector similarity search

## 📞 Contact & Support

For questions and support:
- Open an issue in the repository
- Contact the project lead directly
- Join the development Discord server (invitation in onboarding email)

## 🗺️ Roadmap

### Current Focus (Q1 2025)
- Complete migration to NoSQL
- Implement enhanced search capabilities
- Optimize engagement tracking

### Upcoming Features (Q2 2025)
- Real-time notification system
- Content moderation tools
- Analytics dashboard

### Future Direction
- Mobile API optimization
- GraphQL API integration
- Advanced recommendation engine
