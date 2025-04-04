from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class BlamConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lacos.blam'
    verbose_name = "BLAM"

    def ready(self):
        """
        This method is called when Django starts. 
        Importing the signals module connects the receivers.
        """
        try:
            from . import signals 
            logger.info("BLAM signals registered successfully.")
        except ImportError:
            logger.warning("Could not import BLAM signals (signals.py may be missing/invalid).")
        except Exception as e:
            logger.error(f"Error registering BLAM signals: {e}", exc_info=True)
