#!/bin/bash
# Package extension for Firefox Add-ons

echo "📦 Packaging Vatican Ticket Monitor for Firefox Add-ons..."

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

# Create XPI (ZIP with .xpi extension)
zip -r ../vatican-monitor-firefox.xpi *

cd ..
echo "✅ Package created: dist/vatican-monitor-firefox.xpi"
echo ""
echo "Next steps:"
echo "1. Go to https://addons.mozilla.org/developers/"
echo "2. Create account (free)"
echo "3. Submit New Add-on"
echo "4. Upload vatican-monitor-firefox.xpi"
echo "5. Fill in listing details"
echo "6. Submit for review (1-7 days)"
