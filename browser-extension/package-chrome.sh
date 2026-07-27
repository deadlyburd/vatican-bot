#!/bin/bash
# Package extension for Chrome Web Store

echo "📦 Packaging Vatican Ticket Monitor for Chrome Web Store..."

# Create clean directory
rm -rf dist
mkdir -p dist

# Copy extension files
cp -r browser-extension dist/vatican-monitor
cd dist/vatican-monitor

# Remove unnecessary files
rm -f package-chrome.sh
rm -f package-firefox.sh
rm -f *.md

# Create ZIP
cd ..
zip -r vatican-monitor-chrome.zip vatican-monitor/

echo "✅ Package created: dist/vatican-monitor-chrome.zip"
echo ""
echo "Next steps:"
echo "1. Go to https://chrome.google.com/webstore/devconsole"
echo "2. Pay one-time $5 developer fee"
echo "3. Upload vatican-monitor-chrome.zip"
echo "4. Fill in store listing details"
echo "5. Submit for review (1-3 days)"
