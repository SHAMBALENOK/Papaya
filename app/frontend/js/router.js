function navigate(hash) {
    window.location.hash = hash;
}

function getRoute() {
    const hash = window.location.hash || '#/';
    return hash.slice(1); // remove '#'
}

function router() {
    const path = getRoute();
    const header = document.getElementById('header');

    if (path === '/auth' || path === '/') {
        // check if it's auth or dashboard
    }

    if (path.startsWith('/event/')) {
        header.classList.remove('hidden');
        const eventId = path.split('/event/')[1];
        renderEvent(eventId);
    } else if (path === '/profile') {
        header.classList.remove('hidden');
        renderProfile();
    } else if (path === '/auth') {
        header.classList.add('hidden');
        renderAuth();
    } else {
        // default: dashboard
        header.classList.remove('hidden');
        renderDashboard();
    }
}

window.addEventListener('hashchange', router);