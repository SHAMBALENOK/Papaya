function navigate(hash) { window.location.hash = hash; }

function getRoute() {
    return (window.location.hash || '#/').slice(1);
}

function router() {
    const path = getRoute();
    const header = document.getElementById('header');

    if (path.startsWith('/event/')) {
        header.classList.remove('hidden');
        renderEvent(path.split('/event/')[1]);
    } else if (path === '/profile') {
        header.classList.remove('hidden');
        renderProfile();
    } else if (path === '/auth') {
        header.classList.add('hidden');
        renderAuth();
    } else {
        header.classList.remove('hidden');
        renderDashboard();
    }
}

window.addEventListener('hashchange', router);