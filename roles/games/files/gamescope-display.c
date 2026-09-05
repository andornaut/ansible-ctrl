/* Preloaded into every process of a game container gamescope-child started. Restores the
 * display environment gamescope gave its child, which the flatpak portal has replaced with
 * the host's on the way into the sub-sandbox: README.md. DISPLAY comes back from
 * GAMESCOPE_CHILD_XDISPLAY, and WAYLAND_DISPLAY goes, as gamescope itself unsets it: the
 * Gamescope WSI layer reads a WAYLAND_DISPLAY that is not gamescope's own socket as proof
 * it is not running under gamescope, and then creates a plain swapchain that never presents.
 *
 * WORKAROUND: the sub-sandbox gets the portal's own environment, not the launcher's. Remove
 * once a flatpak the hosts run passes the caller's: https://github.com/flatpak/flatpak/issues/5278 */
#include <stdlib.h>
#include <string.h>

__attribute__((constructor)) static void gamescope_display(void)
{
    const char *want = getenv("GAMESCOPE_CHILD_XDISPLAY");
    const char *have = getenv("DISPLAY");

    if (!want || !*want)
        return;

    if (!have || strcmp(have, want) != 0)
        setenv("DISPLAY", want, 1);

    unsetenv("WAYLAND_DISPLAY");
}
