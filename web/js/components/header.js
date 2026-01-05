/**
 * Header component - handles navigation state
 */
class Header {
    constructor() {
        this.navLinks = document.querySelectorAll('.nav-link');
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
    }

    setActiveNav(page) {
        this.navLinks.forEach(link => {
            if (link.dataset.page === page) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    setStatus(status, text) {
        this.statusDot.className = 'status-dot';

        switch (status) {
            case 'connected':
                this.statusDot.classList.add('connected');
                this.statusText.textContent = text || 'Connected';
                break;
            case 'error':
                this.statusDot.classList.add('error');
                this.statusText.textContent = text || 'Error';
                break;
            default:
                this.statusText.textContent = text || 'Disconnected';
        }
    }
}

window.Header = Header;
