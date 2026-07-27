#!/bin/bash

# Quick test to verify timestamp calculation for August 13, 2026

echo "========================================="
echo "🕐 Vatican Timestamp Test"
echo "========================================="
echo ""
echo "Testing timestamp for: August 13, 2026"
echo ""

# Calculate using Node.js (similar to extension logic)
node << 'EOF'
function getRomeTimezoneOffset(year, month, day) {
    const date = new Date(year, month - 1, day);
    const monthNum = date.getMonth();
    
    // April-September: DST (UTC+2)
    if (monthNum >= 3 && monthNum <= 8) {
        return 120;
    }
    
    // November-February: No DST (UTC+1)
    if (monthNum <= 1 || monthNum >= 10) {
        return 60;
    }
    
    return 60;
}

const day = 13;
const month = 8;
const year = 2026;

// Method 1: Local timezone (WRONG)
const localDate = new Date(year, month - 1, day, 0, 0, 0);
const localTimestamp = localDate.getTime();

// Method 2: Rome timezone (CORRECT)
const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T00:00:00`;
const utcDate = new Date(dateStr + 'Z');
const romeOffset = getRomeTimezoneOffset(year, month, day);
const romeTimestamp = utcDate.getTime() - (romeOffset * 60 * 1000);

console.log("📅 Date: August 13, 2026");
console.log("");
console.log("❌ Local Timezone (WRONG):");
console.log("   Timestamp: " + localTimestamp);
console.log("   ISO: " + localDate.toISOString());
console.log("   URL: https://tickets.museivaticani.va/home/fromtag/1/" + localTimestamp + "/MV-Biglietti/1");
console.log("");
console.log("✅ Rome Timezone (CORRECT):");
console.log("   Timestamp: " + romeTimestamp);
console.log("   ISO: " + new Date(romeTimestamp).toISOString());
console.log("   Rome Offset: UTC+" + (romeOffset / 60) + " hours");
console.log("   URL: https://tickets.museivaticani.va/home/fromtag/1/" + romeTimestamp + "/MV-Biglietti/1");
console.log("");
console.log("📊 Difference: " + Math.abs(localTimestamp - romeTimestamp) + " ms (" + (Math.abs(localTimestamp - romeTimestamp) / 1000 / 60 / 60) + " hours)");
console.log("");
console.log("🔗 Test the correct URL:");
console.log("   https://tickets.museivaticani.va/home/fromtag/1/" + romeTimestamp + "/MV-Biglietti/1");
EOF

echo ""
echo "========================================="
echo "✅ Timestamp calculation complete!"
echo "========================================="
echo ""
echo "Copy the 'CORRECT' URL above and open it in your browser"
echo "to verify it loads August 13, 2026 on Vatican's website."
echo ""
