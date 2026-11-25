#!/bin/bash
echo "🚀 Starting Daily Tech Muchatlu Pipeline..."
cd /workspaces/YOUTUBE
source venv/bin/activate

# Run the pipeline (it will auto-approve Telegram after 5s)
python -m pipeline.main --now

echo "✅ Daily run finished. Check pipeline output for story/upload failures; YouTube visibility follows config.yaml."
