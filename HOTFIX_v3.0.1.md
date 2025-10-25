# SafetyBot v3.0.1 - Hotfix

## Issue Fixed
**Error**: `'NoneType' object has no attribute 'get'` when extracting event data

**Root Cause**: The `extract_event_data()` method was not properly handling `None` values in nested dictionaries. Some events from the API have `None` for the `driver` or `metadata` fields instead of an empty dict `{}`.

## Changes Made

### File: `safetybot.py`
**Method**: `extract_event_data()` (around line 505)

#### Before:
```python
def extract_event_data(self, event: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    """Extract relevant event data for storage"""
    try:
        driver = event.get('driver', {})
        driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown'
        severity = event.get('metadata', {}).get('severity', 'unknown')
        # ... rest of code
```

#### After:
```python
def extract_event_data(self, event: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    """Extract relevant event data for storage"""
    try:
        # Handle None or missing driver dict
        driver = event.get('driver') or {}
        driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown'
        
        # Handle None or missing metadata dict
        metadata = event.get('metadata') or {}
        severity = metadata.get('severity', 'unknown') or 'unknown'
        # ... rest of code
```

**Key Changes**:
1. Line 508: Changed `event.get('driver', {})` to `event.get('driver') or {}`
2. Line 513-514: Changed to handle metadata safely: `metadata = event.get('metadata') or {}`
3. Line 525-527: Added `or 0` to speed values to handle None returns

## Why This Fixes It

- **Defensive coding**: Uses `or {}` pattern to ensure we always have a dict to call `.get()` on
- **Graceful degradation**: If a field is missing, we get sensible defaults (0 for speeds, 'Unknown' for driver name, 'unknown' for severity)
- **No exception bubbling**: The try/except still catches any other issues and logs them

## Deployment

### Option 1: Apply Fix Manually (Linux Server)

Edit `safetybot.py` line 505-553 and apply the changes shown above.

### Option 2: Copy Updated File

```bash
# On your Windows machine (if using WSL or similar):
scp safetybot.py sultan@tms:~/safetybot/safetybot.py

# Or manually copy the updated code and replace the extract_event_data() method
```

### Option 3: Apply the Exact Changes

Replace the `extract_event_data()` method (starting around line 505) with:

```python
def extract_event_data(self, event: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    """Extract relevant event data for storage"""
    try:
        # Handle None or missing driver dict
        driver = event.get('driver') or {}
        driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown'
        
        # Handle None or missing metadata dict
        metadata = event.get('metadata') or {}
        severity = metadata.get('severity', 'unknown') or 'unknown'
        
        extracted = {
            'event_type': event_type,
            'driver_name': driver_name,
            'severity': severity,
            'event_id': event.get('id', 0),
            'timestamp': datetime.now().isoformat()
        }
        
        if event_type == 'speeding':
            start_lat = event.get('start_lat')
            start_lon = event.get('start_lon')
            date_time = self.format_time(event.get('start_time', ''), start_lat, start_lon)
            
            min_speed = event.get('min_vehicle_speed', 0) or 0
            max_speed = event.get('max_vehicle_speed', 0) or 0
            avg_exceeded = event.get('avg_over_speed_in_kph', 0) or 0
            
            min_speed_mph = round(min_speed * 0.621371, 1) if min_speed else 0
            max_speed_mph = round(max_speed * 0.621371, 1) if max_speed else 0
            avg_exceeded_mph = round(avg_exceeded * 0.621371, 1) if avg_exceeded else 0
            
            extracted.update({
                'date_time': date_time,
                'speed_range': f"{min_speed_mph}–{max_speed_mph} mph",
                'exceeded_by': f"+{avg_exceeded_mph} mph"
            })
        else:
            # Performance events
            end_lat = event.get('end_lat')
            end_lon = event.get('end_lon')
            end_time = self.format_time(event.get('end_time', ''), end_lat, end_lon)
            
            extracted.update({
                'date_time': end_time,
                'speed_range': '',
                'exceeded_by': ''
            })
        
        return extracted
    except Exception as e:
        logger.error(f"Error extracting event data: {e}")
        return None
```

## After Applying Fix

1. **Restart the bot**:
   ```bash
   sudo systemctl restart safetybot.service
   ```

2. **Verify the fix**:
   ```bash
   sudo journalctl -u safetybot.service -f
   ```
   
   You should no longer see:
   ```
   Error extracting event data: 'NoneType' object has no attribute 'get'
   ```

3. **Check event storage**:
   ```bash
   ls -la ~/safetybot/events_data/
   cat ~/safetybot/events_data/events_*.json | head -20
   ```

## Version Info

- **Hotfix Version**: v3.0.1
- **Date**: October 25, 2025
- **Status**: Ready for Production
- **Tested**: ✅ Handles None values in nested dicts

---

**After applying this fix, the bot should run without errors!** ✅
