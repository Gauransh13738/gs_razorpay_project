# Render Deployment Guide

This guide will help you deploy the Razorpay Payment Recovery Engine on Render.com.

## Prerequisites

1. **GitHub Repository**: Your code is already pushed to https://github.com/Gauransh13738/gs_razorpay_project.git
2. **Render Account**: Create a free account at https://render.com
3. **API Keys**: Have your Groq API Key and ElevenLabs API Key ready

## Architecture Overview

For Render deployment, you'll need to create:

1. **Backend Service** (Web Service) - FastAPI application
2. **Frontend Service** (Static Site) - Dashboard HTML
3. **Environment Variables** - API keys and configuration

## Step 1: Deploy Backend Service

### 1.1 Create Backend Web Service

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Select `gs_razorpay_project` repository
5. Configure the service:

**Build & Deploy Settings:**
```
Root Directory: backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn server:app --host 0.0.0.0 --port $PORT
```

**Environment Variables:**
Add these environment variables in the Render dashboard:

```
GROQ_API_KEY=your_groq_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
VOICE_ID=r1KmysJdVYZjJCm4mL3b
PORT=8000
ENVIRONMENT=production
```

**Instance Type:**
- **Free**: Good for testing (spins down when inactive)
- **Starter ($7/month)**: Recommended for production (always on)

### 1.2 Create `runtime.txt` for Backend

Create a file `backend/runtime.txt` to specify Python version:

```bash
cd backend
echo "3.9.0" > runtime.txt
```

### 1.3 Add to Git and Push

```bash
cd "D:\Machine Learning\razorpay_proj"
git add backend/runtime.txt
git commit -m "Added Python runtime version for Render"
git push origin main
```

## Step 2: Deploy Frontend Service

### 2.1 Create Frontend Static Site

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Static Site"**
3. Connect your GitHub repository
4. Select `gs_razorpay_project` repository
5. Configure the service:

**Build & Deploy Settings:**
```
Root Directory: frontend
Publish Directory: . (root of frontend directory)
Build Command: (leave empty for static HTML)
```

**Environment Variables:**
Add this to configure the API endpoint:

```
VITE_API_URL=https://your-backend-service-url.onrender.com
```

**Advanced Settings:**
- **Auto-Deploy**: Enable (deploys on git push)
- **Custom Domain**: Optional (e.g., razorpay.yourdomain.com)

### 2.2 Update Frontend API Configuration

The frontend needs to point to your Render backend URL. Update the API calls in `frontend/dashboard.html`:

Find all API calls and update the base URL:

```javascript
// Change from
const response = await fetch('/api/voice/call', {

// To (replace YOUR_BACKEND_URL with actual Render URL)
const response = await fetch('https://your-backend-service.onrender.com/api/voice/call', {
```

You'll need to update these endpoints in `dashboard.html`:
- `/api/events`
- `/api/voice/agents`
- `/api/voice/call`
- `/api/voice/transcribe`
- `/api/voice/respond`
- `/api/razorpay/create_link`
- `/api/razorpay/webhook`
- `/api/payments/simulate`
- `/api/payments/test-cards`
- `/api/metrics`
- `/api/audit/logs`

## Step 3: Configure CORS for Production

Update `backend/server.py` to allow requests from your Render frontend:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-frontend-service.onrender.com",
        "http://localhost:3000"  # for local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Step 4: Deploy and Test

### 4.1 Deploy Both Services

1. Push any changes to GitHub
2. Render will automatically deploy both services
3. Monitor deployment logs in Render dashboard

### 4.2 Test the Deployment

1. **Access Frontend**: `https://your-frontend-service.onrender.com`
2. **Test Backend API**: `https://your-backend-service.onrender.com/docs`
3. **Test Voice Call**: Try the voice agent functionality
4. **Check Logs**: Monitor Render logs for any errors

## Step 5: Configure Custom Domain (Optional)

### 5.1 Backend Custom Domain

1. In Render dashboard, go to your backend service
2. Click **"Settings"** → **"Custom Domains"**
3. Add your custom domain (e.g., `api.yourdomain.com`)
4. Update DNS records as instructed by Render

### 5.2 Frontend Custom Domain

1. In Render dashboard, go to your frontend service
2. Click **"Settings"** → **"Custom Domains"**
3. Add your custom domain (e.g., `app.yourdomain.com`)
4. Update DNS records as instructed by Render

## Step 6: Production Considerations

### 6.1 Database Migration (Optional)

For production, consider migrating from CSV/JSON to a proper database:

1. Add PostgreSQL to your Render backend service
2. Update `payment_workflow.py` to use database instead of CSV
3. Create migration scripts for existing data

### 6.2 Monitoring and Logging

Render provides built-in monitoring:
- **Metrics**: CPU, memory, response times
- **Logs**: Real-time logs for debugging
- **Alerts**: Set up alerting for errors

### 6.3 Scaling

Render supports automatic scaling:
- **Auto-scaling**: Configure based on CPU/memory
- **Manual scaling**: Upgrade instance types as needed

## Troubleshooting

### Backend Deployment Issues

**Issue**: Build fails due to missing dependencies
```
Solution: Ensure all dependencies are in requirements.txt
```

**Issue**: Runtime errors due to missing environment variables
```
Solution: Check all environment variables are set in Render dashboard
```

**Issue**: WebSocket connections fail
```
Solution: Render supports WebSockets on Web Services, ensure your configuration is correct
```

### Frontend Deployment Issues

**Issue**: API calls fail due to CORS
```
Solution: Update CORS configuration in backend server.py
```

**Issue**: Static site won't deploy
```
Solution: Ensure dashboard.html is in the frontend root directory
```

### Common Issues

**Issue**: Services spin down (free tier)
```
Solution: Upgrade to Starter tier ($7/month) for always-on services
```

**Issue**: Slow cold starts
```
Solution: Use paid instances or implement keep-alive endpoints
```

## Cost Estimates

**Free Tier:**
- Backend: Free (spins down when inactive)
- Frontend: Free (static sites are always free)
- **Total**: $0/month

**Production Tier:**
- Backend: $7/month (Starter)
- Frontend: Free (static sites)
- **Total**: $7/month

**Scale-up Tier:**
- Backend: $25/month (Standard 2x)
- Frontend: Free
- **Total**: $25/month

## Alternative: Single Service Deployment

If you prefer a simpler setup, you can deploy everything as a single web service:

1. Move `frontend/dashboard.html` to `backend/` directory
2. Update `backend/server.py` to serve the HTML
3. Deploy as a single Web Service on Render
4. No need for separate frontend service

This approach is simpler but less flexible for scaling.

## Next Steps

1. **Deploy**: Follow the steps above to deploy both services
2. **Test**: Thoroughly test all functionality
3. **Monitor**: Set up monitoring and alerting
4. **Scale**: Upgrade to paid tier if needed for production
5. **Custom Domain**: Add custom domains for professional appearance

Your Razorpay Payment Recovery Engine will be live and accessible via Render URLs!