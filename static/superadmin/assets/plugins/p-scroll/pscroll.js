(function($) {
    "use strict";

    // Only attach scrollbars to containers that exist on the current page
    ['.app-sidebar', '.header-dropdown-list', '.notifications-menu', '.message-menu-scroll'].forEach(function(selector) {
        if (document.querySelector(selector)) {
            new PerfectScrollbar(selector, {
                useBothWheelAxes: true,
                suppressScrollX: true,
                suppressScrollY: false,
            });
        }
    });
})(jQuery);
