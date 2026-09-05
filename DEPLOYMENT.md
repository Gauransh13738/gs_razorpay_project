# Deployment Guide

## Production Deployment

### Option 1: Traditional Server Deployment

1. **Prepare Environment Variables**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env with production API keys
   ```

2. **Install Dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Start Backend Server**
   ```bash
   uvicorn server:app --host 0.0.0.0 --port 8000
   ```

4. **Serve Frontend**
   ```bash
   cd frontend
   python -m http.server 3000
   # Or use nginx/apache for production
   ```

### Option 2: Cloud Deployment (AWS/GCP/Azure)

#### Backend Deployment

1. **Deploy to AWS ECS**
   - Build Docker image: `docker build -t razorpay-backend ./backend`
   - Push to ECR: `docker push your-ecr-repo/razorpay-backend`
   - Deploy to ECS with appropriate task definitions

2. **Deploy to Google Cloud Run**
   ```bash
   gcloud builds submit --tag gcr.io/PROJECT-ID/razorpay-backend ./backend
   gcloud run deploy razorpay-backend --image gcr.io/PROJECT-ID/razorpay-backend --platform managed
   ```

#### Frontend Deployment

1. **Deploy to AWS S3 + CloudFront**
   - Upload `frontend/dashboard.html` to S3 bucket
   - Configure CloudFront distribution with custom domain
   - Set up CORS and caching policies

2. **Deploy to Vercel/Netlify**
   - Connect repository to Vercel/Netlify
   - Configure build settings for static HTML
   - Set environment variables for API endpoint

### Option 3: PaaS Deployment (Heroku/Render/Railway)

#### Heroku Deployment
1. Create a `Procfile` in the backend directory:
   ```
   web: uvicorn server:app --host 0.0.0.0 --port $PORT
   ```

2. Deploy using Heroku CLI:
   ```bash
   heroku create your-app-name
   heroku config:set GROQ_API_KEY=your_key
   heroku config:set ELEVENLABS_API_KEY=your_key
   git push heroku main
   ```

#### Render Deployment
1. Connect your GitHub repository to Render
2. Create a new Web Service
3. Set environment variables in Render dashboard
4. Deploy automatically on push

### Option 4: Virtual Private Server (VPS)

For VPS deployment (DigitalOcean, Linode, AWS EC2):

1. **SSH into your server**
   ```bash
   ssh user@your-server-ip
   ```

2. **Install Python and dependencies**
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip python3-venv nginx
   ```

3. **Set up application**
   ```bash
   git clone https://github.com/Gauransh13738/gs_razorpay_project.git
   cd gs_razorpay_project/backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Configure systemd service**
   ```bash
   sudo nano /etc/systemd/system/razorpay-backend.service
   ```
   ```
   [Unit]
   Description=Razorpay Backend
   After=network.target

   [Service]
   User=your-user
   WorkingDirectory=/path/to/gs_razorpay_project/backend
   ExecStart=/path/to/gs_razorpay_project/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

5. **Start the service**
   ```bash
   sudo systemctl start razorpay-backend
   sudo systemctl enable razorpay-backend
   ```

6. **Configure nginx for frontend**
   ```bash
   sudo nano /etc/nginx/sites-available/razorpay
   ```
   ```
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           root /path/to/gs_razorpay_project/frontend;
           index dashboard.html;
       }

       location /api/ {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }

       location /ws/ {
           proxy_pass http://localhost:8000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }
   }
   ```

## Security Considerations

### 1. API Key Management
- Use environment variables or secret management services
- Never commit `.env` files to version control
- Rotate API keys regularly
- Use different keys for development and production

### 2. HTTPS/TLS
- Enable HTTPS for all endpoints in production
- Use Let's Encrypt for free SSL certificates
- Configure proper SSL/TLS settings in nginx/Apache
- Force HTTPS redirects

### 3. Rate Limiting
- Implement rate limiting on API endpoints
- Use nginx rate limiting or API gateways
- Set appropriate limits based on your traffic patterns
- Consider using slowapi for Python rate limiting

### 4. CORS Configuration
```python
# In production, specify exact origins instead of "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 5. Firewall Configuration
- Configure firewall to only allow necessary ports
- Use fail2ban to prevent brute force attacks
- Keep system and dependencies updated

## Monitoring & Logging

### 1. Application Monitoring
- Set up Prometheus + Grafana for metrics
- Monitor API response times, error rates
- Track voice call success rates

### 2. Logging
- Configure structured logging (JSON format)
- Send logs to centralized logging service (ELK, CloudWatch)
- Set up alerts for critical errors

### 3. Health Checks
```python
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}
```

## Scaling Considerations

### Horizontal Scaling
- Deploy multiple backend instances behind load balancer
- Use Redis for session management if needed
- Consider CDN for static assets

### Database Scaling
- Migrate from CSV/JSON to PostgreSQL for production
- Implement proper indexing and query optimization
- Set up read replicas for reporting queries

## Backup & Disaster Recovery

1. **Regular Backups**
   - Backup database daily
   - Store backups in multiple regions
   - Test restore procedures regularly

2. **High Availability**
   - Deploy across multiple availability zones
   - Implement failover mechanisms
   - Have standby instances ready

## Performance Optimization

1. **Caching**
   - Implement Redis caching for frequently accessed data
   - Cache API responses where appropriate
   - Use CDN for static assets

2. **Async Processing**
   - Move heavy processing to background jobs
   - Use Celery or similar for task queues
   - Implement websocket connection pooling

## Troubleshooting

### Common Issues

1. **WebSocket Connection Fails**
   - Check nginx proxy configuration for WebSocket support
   - Verify timeout settings (may need increase for long calls)
   - Ensure proper CORS headers are set
   - Check firewall rules for WebSocket connections

2. **Audio Transcription Fails**
   - Verify Groq API key is valid and has credits
   - Check audio format compatibility (webm, wav, mp3)
   - Monitor API rate limits and usage
   - Check internet connectivity to Groq API

3. **Voice Generation Slow**
   - Consider caching frequently used phrases
   - Implement fallback TTS providers (EdgeTTS → gTTS)
   - Monitor ElevenLabs API usage and limits
   - Check server resources (CPU/memory)

4. **Server Won't Start**
   - Check if port 8000 is already in use
   - Verify all Python dependencies are installed
   - Check .env file exists and has valid keys
   - Review server logs for specific errors

5. **Frontend Can't Connect to Backend**
   - Verify backend is running on correct port
   - Check CORS configuration
   - Ensure both are on same network/domain
   - Check browser console for CORS errors

## Maintenance

### Regular Tasks
- Update dependencies monthly
- Review and rotate API keys
- Monitor storage usage (audio files)
- Clean up old voice call recordings
- Review audit logs for anomalies

### Updates
- Test updates in staging environment first
- Use blue-green deployment for zero downtime
- Have rollback plans ready