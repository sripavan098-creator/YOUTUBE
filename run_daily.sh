#!/bin/bash
echo "🚀 Starting Daily Tech Muchatlu Pipeline..."
cd /workspaces/YOUTUBE
source venv/bin/activate

# Run the pipeline (it will auto-approve Telegram after 5s)
python -m pipeline.main --now

echo "✅ Daily run complete! Videos are in the out/ folder and uploaded."
