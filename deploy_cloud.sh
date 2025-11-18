#!/bin/bash
# Cloud Deployment Script for PersonaGym-R

set -e

echo "🚀 PersonaGym-R Cloud Deployment"
echo "================================"

# Check if we're in the right directory
if [[ ! -f "agentbeats/green_agent.py" ]]; then
    echo "❌ Error: Please run this script from the personagymattack directory"
    exit 1
fi

echo "✅ Project directory verified"

# Option selection
echo ""
echo "Select deployment option:"
echo "1. Railway (Recommended - Easiest)"
echo "2. Google Cloud Run"
echo "3. Heroku"
echo "4. Docker only (build local image)"

read -p "Enter choice (1-4): " choice

case $choice in
    1)
        echo ""
        echo "🚂 Deploying to Railway"
        echo "======================="
        
        # Check if Railway CLI is installed
        if ! command -v railway &> /dev/null; then
            echo "📦 Installing Railway CLI..."
            npm install -g @railway/cli
        fi
        
        echo "📋 Follow these steps:"
        echo "1. Run: railway login"
        echo "2. Run: railway init"
        echo "3. Run: railway up"
        echo ""
        echo "Your Procfile and railway.json are already configured!"
        echo "Railway will automatically use: agentbeats run_ctrl"
        ;;
        
    2)
        echo ""
        echo "☁️ Deploying to Google Cloud Run"
        echo "================================"
        
        # Build Docker image
        echo "🐳 Building Docker image..."
        docker build -t personagym-green .
        
        # Tag for GCR
        PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "your-project-id")
        docker tag personagym-green gcr.io/$PROJECT_ID/personagym-green
        
        echo "📋 Next steps:"
        echo "1. Set your project: gcloud config set project YOUR_PROJECT_ID"
        echo "2. Push image: docker push gcr.io/$PROJECT_ID/personagym-green"
        echo "3. Deploy: gcloud run deploy personagym-green --image gcr.io/$PROJECT_ID/personagym-green --platform managed --port 8010"
        ;;
        
    3)
        echo ""
        echo "💜 Deploying to Heroku"
        echo "====================="
        
        echo "📋 Follow these steps:"
        echo "1. Run: heroku create your-app-name"
        echo "2. Run: git add ."
        echo "3. Run: git commit -m 'Deploy to Heroku'"
        echo "4. Run: git push heroku main"
        echo ""
        echo "Your Procfile is already configured for Heroku!"
        ;;
        
    4)
        echo ""
        echo "🐳 Building Docker image"
        echo "======================="
        
        docker build -t personagym-green .
        
        echo "✅ Docker image built successfully!"
        echo "To run locally: docker run -p 8010:8000 personagym-green"
        ;;
        
    *)
        echo "❌ Invalid choice. Please run the script again."
        exit 1
        ;;
esac

echo ""
echo "📚 Documentation:"
echo "- See AGENTBEATS_INTEGRATION.md for detailed deployment guide"
echo "- See AGENTBEATS_SUBMISSION.md for AgentBeats submission steps"
echo ""
echo "🎯 Once deployed, update your AgentBeats submission with the new URL!"