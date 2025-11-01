"""HTMX template helper mixin primitives."""

import logging
import json

from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.template.loader import render_to_string

from .bucket_coordinator import BucketCoordinatorMixin
from lacos.storage.services.registry import get_bucket_service

logger = logging.getLogger(__name__)


class HtmxTemplateHelperMixin(BucketCoordinatorMixin):
    """
    Mixin providing common template rendering methods for HTMX-enabled views.

    This reduces code duplication across views where the same templates
    are rendered repeatedly with similar context preparation, especially
    for HTMX out-of-band updates and partial template rendering.
    """

    def render_bucket_tabs_template(self, request, active_bucket=None, success_message=None):
        """
        Render bucket tabs template with standard context.

        Consolidates the repeated pattern:
        - Get workspace buckets
        - Get OCFL buckets
        - Build context
        - Render template
        """
        bucket_service = get_bucket_service()
        workspace_buckets = bucket_service.get_all_accessible_buckets()
        ocfl_buckets = bucket_service.ocfl_buckets

        if active_bucket is not None:
            active_bucket = self.set_active_bucket(request, active_bucket, workspace_buckets)
        else:
            active_bucket = self.get_active_bucket(request, workspace_buckets)

        logger.info(f"🎨 TEMPLATE_HELPER: render_bucket_tabs_template called with {len(workspace_buckets)} buckets")
        logger.info(f"🔧 BUCKET_TABS: Active bucket: {active_bucket}")

        context = {
            'workspace_buckets': workspace_buckets,
            'ocfl_buckets': ocfl_buckets,
            'active_bucket': active_bucket,
            'success_message': success_message,
            'csrf_token': get_token(request),
        }

        return render_to_string(
            'dashboard/bucket_tabs_partial.html',
            context,
            request=request
        )

    def render_bucket_content_template(self, request, bucket_name):
        """
        Render bucket content template with standard context.

        Used for HTMX bucket switching to render the main content area.
        """
        import time

        logger.info("─" * 80)
        logger.info("📦 RENDER BUCKET CONTENT: %s", bucket_name)

        start_time = time.time()

        bucket_service = get_bucket_service()
        force_fresh = request.GET.get('force_fresh', 'false').lower() == 'true'
        workspace_buckets = bucket_service.get_all_accessible_buckets(force_refresh=force_fresh)
        logger.info("Available buckets: %s", workspace_buckets)

        # Verify bucket access
        if bucket_name not in workspace_buckets:
            logger.warning("❌ Bucket not accessible: %s", bucket_name)
            return '<div class="alert alert-error"><span>Bucket not accessible</span></div>'

        logger.info("✅ Bucket access verified")

        self.set_active_bucket(request, bucket_name, workspace_buckets)

        try:
            logger.info("Force fresh: %s", force_fresh)

            # Get bucket structure
            logger.info("Fetching root level items...")
            fetch_start = time.time()

            if force_fresh:
                structure = bucket_service.get_root_level_items(bucket_name, force_fresh=True)
            else:
                structure = bucket_service.get_root_level_items(bucket_name)

            fetch_elapsed = time.time() - fetch_start
            logger.info("✅ Root items fetched in %.2fs", fetch_elapsed)
            logger.info("Items returned: %d", len(structure.get('children', [])))
            logger.info("Has more: %s", structure.get('has_more', False))
            if structure.get('next_token'):
                logger.info("Next token available for pagination")

            context = {
                'structure': structure,
                'bucket_name': bucket_name,
                'bucket_type': bucket_name,  # For backward compatibility
                'ocfl_buckets': bucket_service.ocfl_buckets,
                'csrf_token': get_token(request),
            }

            logger.info("Rendering template...")
            html = render_to_string(
                'dashboard/bucket_content_partial.html',
                context,
                request=request
            )

            total_elapsed = time.time() - start_time
            logger.info("✅ Template rendered (total: %.2fs)", total_elapsed)
            logger.info("─" * 80)

            return html
        except Exception as e:
            logger.error("─" * 80)
            logger.error("❌ RENDER ERROR: %s", bucket_name)
            logger.exception("Error rendering bucket content: %s", str(e))
            logger.error("─" * 80)
            return f'<div class="alert alert-error"><span>Error loading bucket: {str(e)}</span></div>'

    def render_folder_structure_template(self, request, bucket_name, structure=None):
        """
        Render folder structure template for a specific bucket.

        Consolidates the repeated pattern for folder structure rendering.
        """
        bucket_service = get_bucket_service()

        if structure is None:
            try:
                if request.GET.get('force_fresh', 'false').lower() == 'true':
                    structure = bucket_service.get_root_level_items(bucket_name, force_fresh=True)
                else:
                    structure = bucket_service.get_root_level_items(bucket_name)
            except Exception as e:
                logger.exception(f"Error getting structure for {bucket_name}: {str(e)}")
                structure = {
                    "type": "folder",
                    "name": bucket_name,
                    "path": "",
                    "children": []
                }

        context = {
            'structure': structure,
            'bucket_type': bucket_name,
            'csrf_token': get_token(request),
        }

        return render_to_string(
            'dashboard/folder_structure_partial.html',
            context,
            request=request
        )

    def render_bucket_info_template(self, request, bucket_name):
        """
        Render bucket info template (stats, metadata).

        Used for the bucket header information area.
        """
        bucket_service = get_bucket_service()

        try:
            # Get bucket statistics (could be implemented in BucketService)
            # For now, just provide basic info
            is_ocfl = bucket_name in bucket_service.ocfl_buckets

            context = {
                'bucket_name': bucket_name,
                'is_ocfl': is_ocfl,
                'csrf_token': get_token(request),
            }

            return render_to_string(
                'dashboard/bucket_info_partial.html',
                context,
                request=request
            )
        except Exception as e:
            logger.exception(f"Error rendering bucket info for {bucket_name}: {str(e)}")
            return f'<span class="text-error">Error loading info: {str(e)}</span>'

    def render_active_bucket_state_template(self, request, active_bucket, oob=False):
        """Render the hidden input tracking the active bucket selection."""
        context = {
            'active_bucket': active_bucket,
            'oob': oob,
        }

        return render_to_string(
            'dashboard/partials/active_bucket_state.html',
            context,
            request=request
        )

    def build_oob_response(self, main_html, oob_updates=None):
        """
        Build response with out-of-band updates.

        Consolidates the repeated pattern:
        response = f'{main_html}<div id="target" hx-swap-oob="innerHTML">{content}</div>'

        Args:
            main_html (str): The main response HTML
            oob_updates (dict): Dict of {target_id: content} for OOB updates

        Returns:
            str: Complete HTML response with OOB updates
        """
        logger.info(f"🔍 BUILD_OOB DEBUG: main_html length: {len(main_html)}")
        logger.info(f"🔍 BUILD_OOB DEBUG: oob_updates: {list(oob_updates.keys()) if oob_updates else 'None'}")

        if not oob_updates:
            logger.info(f"🔍 BUILD_OOB DEBUG: No OOB updates, returning main_html only")
            return main_html

        oob_html = ""
        for target_id, content in oob_updates.items():
            oob_element = f'<div id="{target_id}" hx-swap-oob="innerHTML">{content}</div>'
            oob_html += oob_element
            logger.info(f"🔍 BUILD_OOB DEBUG: Added OOB element for '{target_id}', content length: {len(content)}")

        final_response = f'{main_html}{oob_html}'
        logger.info(f"🔍 BUILD_OOB DEBUG: Final combined response length: {len(final_response)}")
        return final_response


    def build_bucket_tabs_oob_response(self, main_html="", request=None, active_bucket=None, success_message=None):
        """
        Build response with bucket tabs OOB update using outerHTML swap.

        This is a specialized method for updating bucket tabs since they need
        outerHTML swap (the template includes the complete element with id).

        Args:
            main_html (str): The main response HTML (optional)
            request: The HTTP request object for context
            active_bucket (str): The bucket to mark as active (optional)
            success_message (str): Success message to display (optional)

        Returns:
            str: Complete HTML response with bucket tabs OOB update
        """
        try:
            # Use the existing method to ensure consistency
            tabs_html = self.render_bucket_tabs_template(
                request=request,
                active_bucket=active_bucket,
                success_message=success_message
            )

            active_bucket_resolved = None
            active_bucket_snippet = ""

            if request is not None:
                active_bucket_resolved = self.get_active_bucket(request)
                active_bucket_snippet = self.render_active_bucket_state_template(
                    request=request,
                    active_bucket=active_bucket_resolved,
                    oob=True
                )

            # Add hx-swap-oob="outerHTML" to the bucket-tabs element
            if 'id="bucket-tabs"' in tabs_html:
                oob_tabs_html = tabs_html.replace(
                    'id="bucket-tabs"',
                    'id="bucket-tabs" hx-swap-oob="outerHTML"',
                    1
                )
                return f'{main_html}{oob_tabs_html}{active_bucket_snippet}'
            else:
                logger.warning("bucket-tabs id not found in tabs HTML, falling back to innerHTML")
                return f"{self.build_oob_response(main_html, {'bucket-tabs': tabs_html})}{active_bucket_snippet}"

        except Exception as e:
            logger.exception(f"Error building bucket tabs OOB response: {str(e)}")
            return main_html

    def add_htmx_trigger(self, html_content, trigger_events=None):
        """
        Add HTMX trigger header for event synchronization.

        This method adds an HX-Trigger header to fire custom events
        that other parts of the interface can listen for.

        Args:
            html_content (str): The HTML content to wrap in an HttpResponse
            trigger_events (dict): Dict of event names and data to trigger

        Returns:
            HttpResponse: Response with HX-Trigger header
        """
        response = HttpResponse(html_content)

        if trigger_events:
            response['HX-Trigger'] = json.dumps(trigger_events)
            logger.info(f"🔔 HTMX_TRIGGER: Added triggers: {list(trigger_events.keys())}")

        return response

    def build_standard_bucket_refresh_response(self, request, bucket_name, main_html="", success_message=None):
        """
        Build a standard response that refreshes bucket-related UI components.

        This is commonly needed after operations that change the bucket state.
        Returns main_html + OOB updates for bucket tabs, content, and info.
        """
        self.set_active_bucket(request, bucket_name)

        # Render all standard templates
        tabs_html = self.render_bucket_tabs_template(request, active_bucket=bucket_name, success_message=success_message)
        content_html = self.render_bucket_content_template(request, bucket_name)
        info_html = self.render_bucket_info_template(request, bucket_name)

        # Build OOB updates
        oob_updates = {
            'bucket-tabs': tabs_html,
            'bucket-content': content_html,
            'bucket-info': info_html,
        }

        response_html = self.build_oob_response(main_html, oob_updates)

        active_bucket_snippet = self.render_active_bucket_state_template(
            request=request,
            active_bucket=self.get_active_bucket(request),
            oob=True,
        )

        return f'{response_html}{active_bucket_snippet}'

    def render_message_template(self, message, level="success"):
        """
        Render message template for displaying notifications.

        Args:
            message (str): The message to display
            level (str): Message level - 'success', 'error', 'warning', 'info'

        Returns:
            str: Rendered message HTML
        """
        alert_classes = {
            'success': 'alert-success',
            'error': 'alert-error',
            'warning': 'alert-warning',
            'info': 'alert-info',
        }

        alert_class = alert_classes.get(level, 'alert-info')

        icon_paths = {
            'success': "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
            'error': "M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z",
            'warning': "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16c-.77.833.192 2.5 1.732 2.5z",
            'info': "M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
        }

        icon_path = icon_paths.get(level, icon_paths['info'])

        return f'''
        <div class="alert {alert_class}">
            <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="{icon_path}" />
            </svg>
            <span>{message}</span>
        </div>
        '''
