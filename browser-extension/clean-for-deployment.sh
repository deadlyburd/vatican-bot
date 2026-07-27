#!/bin/bash
# Clean Extension for Deployment
# This script removes development files and creates a clean package

echo "🧹 Cleaning extension for deployment..."

# Remove development/debug files
rm -f ticketsa.museivaticani.va.har
rm -f create-icons.html

# Remove all markdown documentation (keep only essential ones)
# Keep: README.md, INSTALLATION.md, QUICK_START.md
rm -f AUTO_BOOKING_GUIDE.md
rm -f BACKEND_LISTENER_GUIDE.md
rm -f BACKEND_LISTENER_MODE.md
rm -f CHANGELOG.md
rm -f DEBUG_FALSE_NEGATIVES.md
rm -f DEBUG_TAB_RELOAD.md
rm -f DEEP_CHECK_MODE.md
rm -f DEPLOYMENT_CHECKLIST.md
rm -f EXTENSION_SUMMARY.md
rm -f FIX_RELOAD_LOOP.md
rm -f MULTI_BOOKING_SOLUTION.md
rm -f PACKAGE_LOCAL.md
rm -f QUICK_REFERENCE.md
rm -f QUICK_VISUAL_CHECK.md
rm -f RATE_LIMIT_GUIDE.md
rm -f STRICT_TIME_SELECTION.md
rm -f TAB_RELOAD_MODE.md
rm -f TEST_GUIDE.md
rm -f TESTING_GUIDE.md
rm -f TIMING_AND_HOLD_MODE.md
rm -f VISUAL_CHECK_MODE.md

echo "✅ Cleaned development files"

# Create deployment package
PACKAGE_NAME="vatican-auto-booking-extension-v1.0.zip"

echo "📦 Creating deployment package: $PACKAGE_NAME"

# Create zip with only essential files
zip -r "../$PACKAGE_NAME" \
  manifest.json \
  background.js \
  content.js \
  popup.html \
  popup.js \
  popup.css \
  options.html \
  options.js \
  settings.html \
  settings.js \
  icons/ \
  README.md \
  INSTALLATION.md \
  QUICK_START.md \
  -x "*.DS_Store" "*.git*"

echo "✅ Package created: $PACKAGE_NAME"
echo ""
echo "📋 Package contents:"
echo "   - Core files: manifest.json, background.js, content.js"
echo "   - UI files: popup.*, options.*, settings.*"
echo "   - Icons: icons/"
echo "   - Documentation: README.md, INSTALLATION.md, QUICK_START.md"
echo ""
echo "🚀 Ready to deploy to other computers!"
echo "   1. Copy $PACKAGE_NAME to target computer"
echo "   2. Unzip the file"
echo "   3. Load unpacked extension in Chrome"
