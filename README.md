# VenomX FastAPI Backend Server

## Overview

VenomX is a comprehensive snake identification and antivenom finder system built with FastAPI. The backend provides two major features:

1. **Snake Identification**: Upload an image to identify snake species using AI models
2. **Antivenom Finder**: Find nearby healthcare facilities with appropriate antivenom

## Features

### Snake Identification
- YOLOv8s-obb object detection for snake detection and cropping
- YOLOv8s classification for species identification
- Confidence analysis and recommendations
- Database integration for species information

###Antivenom Finder
- Find facilities with specific antivenom
- Distance and travel time calculation using OSRM
- Facility details with stock information
- Location-based sorting

### Technical Features
- FastAPI framework with automatic API documentation
- Supabase/PostgreSQL integration
- Docker containerization
- Production-ready with proper error handling
- Comprehensive logging and monitoring

## Tech Stack

- **Framework**: FastAPI
- **Database**: Supabase (PostgreSQL)
- **AI Models**: YOLOv8s (PyTorch)
- **Routing**: OSRM API
- **Containerization**: Docker
- **Environment Management**: python-dotenv

## Prerequisites

### Required
- Python 3.11+
- Docker and Docker Compose
- 4GB+ RAM (for AI models)

### AI Models
Place your trained models in the `models/` directory:
- `snake_detection.pt` - YOLOv8s-obb detection model
- `snake_classification.pt` - YOLOv8s classification model

### Supabase Setup
1. Create a Supabase project
2. Import the provided database schema
3. Get your project URL and API keys

## Quick Start

### 1. Clone and Setup
```bash
git clone <your-repo>
cd server
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and configure:

```env
# Database Configuration
DATABASE_URL=postgresql://postgres.djhgshxjgzalqssmxsyf:[YOUR_PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres

# Supabase Configuration
SUPABASE_URL=https://djhgshxjgzalqssmxsyf.supabase.co
SUPABASE_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key

# Model Configuration
DETECTION_MODEL_PATH=models/snake_detection.pt
CLASSIFICATION_MODEL_PATH=models/snake_classification.pt
```

### 3. Docker Deployment (Recommended)

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

The API will be available at `http://localhost:8000`

### 4. Manual Setup (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API Documentation

Once running, access the interactive API documentation:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## API Endpoints

### Health Check
```
GET /health
GET /
```

### Snake Identification
```
POST /api/v1/snake-id
- Upload image file
- Returns detection and classification results
- Includes database lookup for species info
```

### Antivenom Finder
```
POST /api/v1/antivenom/finder
- Find facilities with antivenom for specific snake
- Calculate distances and travel times
- Sort by proximity

POST /api/v1/antivenom/facilities
- List facilities with specific antivenom
- Detailed facility and stock information
```

### Utility Endpoints
```
GET /api/v1/models/info
GET /api/v1/snakes
GET /api/v1/snakes/{scientific_name}
GET /api/v1/antivenom/test-route
```

## Usage Examples

### Snake Identification
```bash
curl -X POST "http://localhost:8000/api/v1/snake-id" \
  -H "Content-Type: multipart/form-data" \
  -F "image=@snake_photo.jpg" \
  -F "confidence_threshold=0.5"
```

### Find Antivenom
```bash
curl -X POST "http://localhost:8000/api/v1/antivenom/finder" \
  -H "Content-Type: application/json" \
  -d '{
    "snake_scientific_name": "Naja naja",
    "user_latitude": 14.5995,
    "user_longitude": 120.9842,
    "max_distance_km": 100
  }'
```

## Database Schema

The application uses the VenomX database schema with the following key tables:

- `snakes` - Snake species information
- `facilities` - Healthcare facilities
- `antivenoms` - Antivenom products
- `facility_antivenom_stock` - Stock levels
- `antivenom_snake_targets` - Snake-antivenom relationships

### Sample Queries

```sql
-- Find all antivenoms for a specific snake
SELECT a.product_name, a.manufacturer 
FROM antivenoms a
JOIN antivenom_snake_targets ast ON a.antivenom_id = ast.antivenom_id
JOIN snakes s ON ast.snake_id = s.snake_id
WHERE s.scientific_name = 'Naja naja';

-- Find facilities with stock
SELECT f.facility_name, fas.quantity, fas.expiration_date
FROM facilities f
JOIN facility_antivenom_stock fas ON f.facility_id = fas.facility_id
WHERE f.is_verified = true AND fas.quantity > 0;
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `SUPABASE_URL` | Supabase project URL | - |
| `SUPABASE_KEY` | Supabase anon key | - |
| `SUPABASE_SERVICE_KEY` | Supabase service role key | - |
| `OSRM_BASE_URL` | OSRM routing service URL | `https://router.project-osrm.org` |
| `DETECTION_MODEL_PATH` | Path to detection model | `models/snake_detection.pt` |
| `CLASSIFICATION_MODEL_PATH` | Path to classification model | `models/snake_classification.pt` |
| `MAX_FILE_SIZE` | Maximum upload size (bytes) | `10485760` (10MB) |
| `ENVIRONMENT` | Environment mode | `development` |

### File Upload Limits
- Maximum file size: 10MB
- Supported formats: JPG, JPEG, PNG, WEBP
- Files are temporarily stored and automatically cleaned up

## Docker Configuration

### Production Deployment
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  venomx-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
    volumes:
      - ./models:/app/models:ro
      - ./logs:/app/logs
    restart: unless-stopped
```

### With Nginx (Recommended for Production)
```nginx
# nginx.conf
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://venomx-api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    client_max_body_size 20M;
}
```

## Performance Optimization

### Model Loading
- Models are loaded once at startup
- GPU acceleration when available
- Memory pooling for database connections

### Caching (Optional)
```yaml
# Add Redis for caching
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
```

### Resource Requirements
- **Minimum**: 2GB RAM, 1 CPU core
- **Recommended**: 4GB RAM, 2 CPU cores
- **Storage**: 500MB for models + temp files

## Monitoring and Logging

### Health Checks
```bash
# Basic health check
curl http://localhost:8000/health

# Model status
curl http://localhost:8000/api/v1/models/info
```

### Logs
- Application logs: `/app/logs/`
- Docker logs: `docker-compose logs -f venomx-api`
- Log levels: INFO, WARNING, ERROR

### Metrics
Monitor these key metrics:
- Response times for `/snake-id` endpoint
- Model inference times
- Database query performance
- File upload success rates

## Troubleshooting

### Common Issues

**1. Model Loading Errors**
```bash
# Check model files exist
ls -la models/

# Check file permissions
chmod 644 models/*.pt
```

**2. Database Connection**
```bash
# Test database connection
python -c "
from app.utils.db import init_db
import asyncio
asyncio.run(init_db())
"
```

**3. OSRM Routing Errors**
```bash
# Test OSRM endpoint
curl "https://router.project-osrm.org/route/v1/driving/121.0244,14.5547;120.9842,14.5995"
```

**4. Memory Issues**
- Reduce batch sizes in models
- Increase Docker memory limits
- Use CPU instead of GPU if needed

### Debug Mode
```bash
# Run with debug logging
docker-compose -f docker-compose.debug.yml up
```

## Development

### Setup Development Environment
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/

# Run with auto-reload
uvicorn main:app --reload
```

### Code Structure
```
server/
├── app/
│   ├── routers/          # API endpoints
│   ├── utils/            # Utilities (DB, AI models, OSRM)
│   ├── models/           # Pydantic models
│   └── __init__.py
├── models/               # AI model files (.pt)
├── temp/                 # Temporary file storage
├── main.py              # FastAPI application
├── requirements.txt     # Dependencies
├── Dockerfile          # Container definition
├── docker-compose.yml  # Docker services
└── README.md           # This file
```

### Adding New Endpoints
1. Create router in `app/routers/`
2. Add to `main.py`
3. Update API documentation
4. Add tests

## Security Considerations

### Production Checklist
- [ ] Change default Supabase keys
- [ ] Set strong database password
- [ ] Configure CORS properly
- [ ] Enable HTTPS
- [ ] Set up rate limiting
- [ ] Monitor file uploads
- [ ] Regular security updates

### Best Practices
- Use environment variables for secrets
- Validate all inputs
- Sanitize file uploads
- Monitor for unusual activity
- Regular backups

## Support

### Getting Help
1. Check the logs for error messages
2. Verify configuration files
3. Test individual components
4. Check database connectivity
5. Validate model files

### Reporting Issues
Include:
- Error messages and logs
- Configuration (without secrets)
- Steps to reproduce
- Environment details

## License

This project is part of the VenomX system for snake identification and antivenom finding.

---

## Quick Reference

### Essential Commands
```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild after changes
docker-compose up --build

# Check health
curl http://localhost:8000/health
```

### File Locations
- **API Docs**: `http://localhost:8000/docs`
- **Models**: `./models/`
- **Logs**: `./logs/`
- **Uploads**: `./temp/`
- **Config**: `.env`
