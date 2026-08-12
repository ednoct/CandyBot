# === IMPORTS ===
import datetime
try:
    import jdatetime
except ImportError:
    jdatetime = None
import time

# === JALALI DATE FORMATTER ===
def get_jalali_date(timestamp: int = None, format_str: str = "%Y/%m/%d %H:%M:%S") -> str:
    """
    Converts a UNIX timestamp to a Jalali (Persian) date string.
    Replaces the legacy jdf.php module.
    """
    if timestamp is None:
        timestamp = int(time.time())
        
    dt = datetime.datetime.fromtimestamp(timestamp)
    
    if jdatetime:
        # If jdatetime is installed, use it for accurate Jalali dates
        jdt = jdatetime.datetime.fromgregorian(datetime=dt)
        return jdt.strftime(format_str)
    else:
        # Fallback to gregorian if not installed
        return dt.strftime(format_str)

def get_current_jalali() -> str:
    """Returns the current date and time in Jalali format."""
    return get_jalali_date(format_str="%Y/%m/%d %H:%M:%S")
