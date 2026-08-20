# === IMPORTS ===
"""
logger.py
---------
Module containing functionalities for logger.
"""
import os
import json
import logging
import traceback
from datetime import datetime

class CandyLogger:
    """Class representing CandyLogger."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    
    _log_dir = None
    _min_level = logging.INFO
    
    @classmethod
    def init(cls, log_dir=None):
        """Handles init."""
        if log_dir is None:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            cls._log_dir = os.path.join(base_dir, 'logs')
        else:
            cls._log_dir = log_dir
            
        if not os.path.exists(cls._log_dir):
            os.makedirs(cls._log_dir, mode=0o775, exist_ok=True)
            
        env_level = os.environ.get('CANDY_LOG_LEVEL', 'info').lower()
        levels = {'debug': cls.DEBUG, 'info': cls.INFO, 'warning': cls.WARN, 'error': cls.ERROR, 'critical': cls.CRITICAL}
        cls._min_level = levels.get(env_level, cls.INFO)
        
    @classmethod
    def set_min_level(cls, level: str):
        """Handles set min level."""
        levels = {'debug': cls.DEBUG, 'info': cls.INFO, 'warning': cls.WARN, 'error': cls.ERROR, 'critical': cls.CRITICAL}
        if level.lower() in levels:
            cls._min_level = levels[level.lower()]
            
    @classmethod
    def log(cls, level: int, message: str, context: dict = None):
        """Handles log."""
        if cls._log_dir is None:
            cls.init()
            
        if level < cls._min_level:
            return
            
        entry = {
            'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': logging.getLevelName(level).lower(),
            'msg': message,
            'ip': context.get('ip', '0.0.0.0') if context else '0.0.0.0',
            'method': context.get('method', 'CLI') if context else 'CLI',
            'uri': context.get('uri', '') if context else ''
        }
        
        if context:
            ctx_clean = {k: v for k, v in context.items() if k not in ['ip', 'method', 'uri']}
            if ctx_clean:
                entry['ctx'] = cls._sanitise_context(ctx_clean)
                
        try:
            line = json.dumps(entry, ensure_ascii=False)
        except Exception:
            line = json.dumps({"ts": entry['ts'], "level": entry['level'], "msg": "<unencodable log entry>"})
            
        filename = f"api-{datetime.now().strftime('%Y-%m-%d')}.log"
        filepath = os.path.join(cls._log_dir, filename)
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception as e:
            logging.error(f"[CandyLogger fallback] {line}")
            
    @classmethod
    def debug(cls, msg: str, ctx: dict = None): cls.log(cls.DEBUG, msg, ctx)
    @classmethod
    def info(cls, msg: str, ctx: dict = None): cls.log(cls.INFO, msg, ctx)
    @classmethod
    def warn(cls, msg: str, ctx: dict = None): cls.log(cls.WARN, msg, ctx)
    @classmethod
    def error(cls, msg: str, ctx: dict = None): cls.log(cls.ERROR, msg, ctx)
    @classmethod
    def critical(cls, msg: str, ctx: dict = None): cls.log(cls.CRITICAL, msg, ctx)
    
    @classmethod
    def exception(cls, e: Exception, note: str = '', ctx: dict = None):
        """Handles exception."""
        if ctx is None: ctx = {}
        ctx['exception'] = e.__class__.__name__
        ctx['trace'] = cls._short_trace(e)
        msg = f"{note}: {str(e)}" if note else str(e)
        cls.log(cls.ERROR, msg, ctx)
        
    @classmethod
    def _short_trace(cls, e: Exception) -> str:
        """Handles  short trace."""
        tb = traceback.extract_tb(e.__traceback__)
        frames = []
        for i, frame in enumerate(tb[:6]):
            where = f"{frame.filename}:{frame.lineno}"
            what = frame.name
            frames.append(f"#{i} {where} {what}")
        return " | ".join(frames)
        
    @classmethod
    def _sanitise_context(cls, ctx: dict) -> dict:
        """Handles  sanitise context."""
        blocked = ['password', 'passwd', 'token', 'apikey', 'api_key', 'secret', 'authorization']
        sanitized = {}
        for k, v in ctx.items():
            if str(k).lower() in blocked:
                sanitized[k] = '***'
            elif isinstance(v, dict):
                sanitized[k] = cls._sanitise_context(v)
            elif isinstance(v, str) and len(v) > 2000:
                sanitized[k] = v[:2000] + '…(truncated)'
            else:
                sanitized[k] = v
        return sanitized
