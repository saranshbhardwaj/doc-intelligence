import json
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SimpleAnalytics:
    """Simple file-based analytics tracking"""
    
    def __init__(self, analytics_dir: Path):
        self.analytics_dir = analytics_dir
        self.analytics_dir.mkdir(parents=True, exist_ok=True)
    
    def track_event(self, event_type: str, **kwargs):
        """Track an analytics event"""
        try:
            event = {
                "event_type": event_type,
                "timestamp": datetime.now().isoformat(),
                **kwargs
            }
            
            # Append to daily log file
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = self.analytics_dir / f"events_{date_str}.jsonl"
            
            # Append as JSONL (one JSON per line)
            with log_file.open("a") as f:
                f.write(json.dumps(event) + "\n")
            
            logger.debug(f"Analytics event tracked: {event_type}")
            
        except Exception as e:
            logger.warning(f"Failed to track analytics: {e}")
    
    def get_stats(self, days: int = 7):
        """Get basic stats from last N days"""
        from collections import Counter
        from datetime import timedelta
        
        stats = {
            "total_events": 0,
            "events_by_type": Counter(),
            "unique_ips": set(),
            "daily_uploads": Counter()
        }
        
        cutoff = datetime.now() - timedelta(days=days)
        
        for log_file in self.analytics_dir.glob("events_*.jsonl"):
            try:
                with log_file.open() as f:
                    for line in f:
                        event = json.loads(line.strip())
                        event_time = datetime.fromisoformat(event["timestamp"])
                        
                        if event_time < cutoff:
                            continue
                        
                        stats["total_events"] += 1
                        stats["events_by_type"][event["event_type"]] += 1
                        
                        if "client_ip" in event:
                            stats["unique_ips"].add(event["client_ip"])
                        
                        if event["event_type"] == "upload_success":
                            date_key = event_time.strftime("%Y-%m-%d")
                            stats["daily_uploads"][date_key] += 1
            
            except Exception as e:
                logger.warning(f"Error reading analytics file {log_file}: {e}")
        
        stats["unique_ips"] = len(stats["unique_ips"])
        stats["events_by_type"] = dict(stats["events_by_type"])
        stats["daily_uploads"] = dict(stats["daily_uploads"])
        
        return stats