# 🎫 Vatican Ticket Monitor - Browser Extension

A Chrome/Firefox extension that monitors Vatican Museums ticket availability in real-time and notifies you when tickets become available.

## Features

✅ **Real-time Monitoring** - Checks Vatican ticket availability at your specified intervals (5s - 60s)
✅ **Smart Notifications** - Desktop notifications when tickets become available
✅ **Multiple Ticket Types** - Supports both standard entry and guided tours
✅ **Language Selection** - Choose language for guided tours (English, Italian, French, German, Spanish)
✅ **Visitor Configuration** - Monitor for 1-20 visitors
✅ **History Tracking** - View recent check results and available slots
✅ **Privacy-Focused** - All data stored locally, no external servers
✅ **Vatican Bot Rules Compliant** - Uses Search API + timeavail API (no hardcoded IDs)

## Installation

### Chrome/Edge

1. Download or clone this repository
2. Open Chrome and go to `chrome://extensions/`
3. Enable "Developer mode" (toggle in top right)
4. Click "Load unpacked"
5. Select the `browser-extension` folder
6. The extension icon will appear in your toolbar

### Firefox

1. Download or clone this repository
2. Open Firefox and go to `about:debugging#/runtime/this-firefox`
3. Click "Load Temporary Add-on"
4. Navigate to the `browser-extension` folder and select `manifest.json`
5. The extension will be loaded temporarily

**Note:** For permanent installation in Firefox, you need to sign the extension through Mozilla Add-ons.

## Usage

### Quick Start

1. Click the extension icon in your toolbar
2. Select your desired date
3. Choose number of visitors
4. Select ticket type (Standard Entry or Guided Tour)
5. If guided tour, select language
6. Choose check interval (5 seconds recommended for fast alerts)
7. Click "Start Monitoring"

### When Tickets Are Found

- You'll receive a desktop notification
- Available slots will appear in the extension popup
- Click "Book Now" to open the Vatican booking page

### Advanced Settings

Click "⚙️ Advanced Settings" to configure:
- Notification preferences
- Auto-stop after finding slots
- History retention
- Request timeout and retries

## How It Works

The extension follows the Vatican Bot Rules:

1. **Search API Call** - Gets fresh ticket IDs for your date/visitors
   ```
   GET /api/search/resultPerTag?lang=it&visitorNum=1&visitDate=01/06/2026&...
   ```

2. **Ticket Matching** - Finds the correct ticket by name (not hardcoded ID)
   - Standard: "Musei Vaticani - Biglietti d'ingresso"
   - Guided: "Musei Vaticani - Visite Guidate"

3. **Time Availability Check** - Gets available time slots
   ```
   GET /api/visit/timeavail?lang=it&visitLang=&visitTypeId=<fresh_id>&...
   ```

4. **Notification** - Alerts you when AVAILABLE slots are found

## Architecture

```
browser-extension/
├── manifest.json          # Extension configuration
├── popup.html            # Main UI
├── popup.css             # Styling
├── popup.js              # UI logic
├── background.js         # Background monitoring service
├── options.html          # Settings page
├── options.js            # Settings logic
├── icons/                # Extension icons
└── README.md            # This file
```

## API Compliance

This extension follows the **Vatican Bot Mandatory Rules**:

✅ Always uses Search API to get fresh ticket IDs
✅ Never uses hardcoded ticket IDs
✅ Matches tickets by name, not ID
✅ Includes `visitLang` parameter (empty for standard, language code for guided)
✅ Uses Rome timezone for date calculations
✅ Filters for AVAILABLE status only

## Privacy

- **No external servers** - All data stored locally in your browser
- **No tracking** - No analytics or user tracking
- **No data collection** - Your monitoring preferences stay on your device
- **Direct API calls** - Extension communicates directly with Vatican website

## Limitations

- **Browser must be open** - Monitoring only works when browser is running
- **Alarm precision** - Chrome alarms have ~1 minute precision (not exact seconds)
- **Rate limiting** - Vatican may rate-limit frequent requests
- **No auto-booking** - Extension only monitors and notifies (you must book manually)

## Troubleshooting

### Extension not checking?
- Make sure browser is open
- Check if monitoring is active (green status badge)
- Verify date is in the future
- Check browser console for errors

### No notifications?
- Enable notifications in browser settings
- Check extension permissions
- Verify "Desktop notifications" is enabled in settings

### API errors?
- Vatican website may be down temporarily
- Try increasing check interval
- Check if date is too far in future (Vatican may not have released tickets yet)

## Development

### Testing Locally

1. Make changes to the code
2. Go to `chrome://extensions/`
3. Click the refresh icon on the extension card
4. Test your changes

### Building for Production

For Chrome Web Store:
```bash
zip -r vatican-monitor.zip browser-extension/ -x "*.git*" "*.DS_Store"
```

For Firefox Add-ons:
```bash
cd browser-extension
zip -r ../vatican-monitor.xpi * -x "*.git*" "*.DS_Store"
```

## Comparison with Backend System

| Feature | Browser Extension | Backend System |
|---------|------------------|----------------|
| Setup | Easy (1-click install) | Complex (Docker, database) |
| Monitoring | Browser must be open | 24/7 monitoring |
| Multiple dates | One at a time | 60+ dates simultaneously |
| Multiple users | Single user | Multiple agencies |
| Auto-booking | No | Yes (snipe mode) |
| Telegram | No | Yes |
| Scalability | Limited | High |

## Future Enhancements

- [ ] Multiple date monitoring
- [ ] Telegram integration
- [ ] Auto-booking (with user confirmation)
- [ ] Price tracking
- [ ] Calendar view
- [ ] Export results to CSV
- [ ] Multi-language UI

## License

MIT License - Feel free to modify and distribute

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review browser console for errors
3. Verify Vatican website is accessible

## Credits

Based on the Vatican Bot monitoring system with Vatican Bot Rules compliance.

---

**Version:** 1.0.0  
**Last Updated:** April 28, 2026  
**Status:** Production Ready ✅
