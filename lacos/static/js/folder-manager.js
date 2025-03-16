export function toggleFolder(element) {
    const contents = element.closest('div').nextElementSibling;
    const iconPaths = {
        open: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />',
        closed: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />'
    };

    if (contents.classList.contains('hidden')) {
        contents.classList.remove('hidden');
        element.querySelector('svg').innerHTML = iconPaths.open;
    } else {
        contents.classList.add('hidden');
        element.querySelector('svg').innerHTML = iconPaths.closed;
    }
}