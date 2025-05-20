/**
 * Main JavaScript file for PizzaJobs application
 */

document.addEventListener('DOMContentLoaded', function() {
    // Set up Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Set up Bootstrap popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function(popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-dismiss alerts 
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 180000);

    // Handle online/in-person interview form toggle
    const isOnlineCheckbox = document.getElementById('id_is_online');
    const meetingLinkField = document.getElementById('div_id_meeting_link');
    const locationField = document.getElementById('div_id_location');

    if (isOnlineCheckbox && meetingLinkField && locationField) {
        // Function to toggle visibility based on checkbox
        function toggleInterviewFields() {
            if (isOnlineCheckbox.checked) {
                meetingLinkField.style.display = 'block';
                locationField.style.display = 'none';
            } else {
                meetingLinkField.style.display = 'none';
                locationField.style.display = 'block';
            }
        }

        // Set initial state
        toggleInterviewFields();

        // Add event listener for changes
        isOnlineCheckbox.addEventListener('change', toggleInterviewFields);
    }

    // Add animation to statistic counters
    const counters = document.querySelectorAll('.counter');
    
    if (counters.length > 0) {
        counters.forEach(counter => {
            const target = parseInt(counter.getAttribute('data-target'));
            const duration = 2000; // Animation duration in milliseconds
            const step = target / (duration / 16); // 60fps approximately
            
            let count = 0;
            const updateCounter = () => {
                if (count < target) {
                    count += step;
                    counter.innerText = Math.min(Math.round(count), target);
                    requestAnimationFrame(updateCounter);
                } else {
                    counter.innerText = target;
                }
            };
            
            updateCounter();
        });
    }

    // Form validation for resume upload
    const resumeUploadForm = document.querySelector('form[enctype="multipart/form-data"]');
    if (resumeUploadForm) {
        resumeUploadForm.addEventListener('submit', function(event) {
            const fileInput = document.getElementById('id_file');
            if (fileInput && fileInput.files.length > 0) {
                const file = fileInput.files[0];
                const fileSize = file.size / 1024 / 1024; // Convert to MB
                const fileType = file.type;
                
                // Check file size (5MB limit)
                if (fileSize > 5) {
                    event.preventDefault();
                    alert('File size exceeds 5MB limit. Please choose a smaller file.');
                    return false;
                }
                
                // Check file type
                const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
                if (!allowedTypes.includes(fileType)) {
                    event.preventDefault();
                    alert('Only PDF and Word documents are allowed.');
                    return false;
                }
            }
        });
    }

    // Sticky navigation behavior
    window.addEventListener('scroll', function() {
        const navbar = document.querySelector('.navbar');
        if (navbar) {
            if (window.scrollY > 50) {
                navbar.classList.add('shadow');
            } else {
                navbar.classList.remove('shadow');
            }
        }
    });

    // Mobile navigation close after click
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    const navbarCollapse = document.querySelector('.navbar-collapse');
    
    if (navLinks.length > 0 && navbarCollapse) {
        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 992) { // Bootstrap lg breakpoint
                    const bsNavbar = bootstrap.Collapse.getInstance(navbarCollapse);
                    if (bsNavbar) {
                        bsNavbar.hide();
                    }
                }
            });
        });
    }

    // Filter enhancement for applications/vacancies list
    const filterForm = document.querySelector('form[method="get"]');
    if (filterForm) {
        const selects = filterForm.querySelectorAll('select');
        selects.forEach(select => {
            select.addEventListener('change', function() {
                // Auto-submit the form when a filter changes
                // But we'll add a slight delay for better UX
                setTimeout(() => {
                    filterForm.submit();
                }, 100);
            });
        });
    }

    // Form field character counter
    const textareas = document.querySelectorAll('textarea[maxlength]');
    textareas.forEach(textarea => {
        // Create counter element
        const counter = document.createElement('small');
        counter.className = 'text-muted d-block text-end';
        counter.innerHTML = `<span>${textarea.value.length}</span>/${textarea.getAttribute('maxlength')} characters`;
        
        // Insert after textarea
        textarea.parentNode.insertBefore(counter, textarea.nextSibling);
        
        // Update counter on input
        textarea.addEventListener('input', function() {
            const currentLength = this.value.length;
            const maxLength = this.getAttribute('maxlength');
            counter.querySelector('span').textContent = currentLength;
            
            // Change color when approaching limit
            if (currentLength > maxLength * 0.9) {
                counter.classList.add('text-danger');
            } else {
                counter.classList.remove('text-danger');
            }
        });
    });
});

// Confirmation for critical actions
function confirmAction(message) {
    return confirm(message);
}

// Function to format date strings
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
    });
}

// Helper function for vacancy filtering
function filterVacancies() {
    const city = document.getElementById('city').value;
    const position = document.getElementById('position_type').value;
    const restaurant = document.getElementById('restaurant').value;
    
    // Construct URL with query parameters
    let url = window.location.pathname + '?';
    if (city) url += `city=${encodeURIComponent(city)}&`;
    if (position) url += `position_type=${encodeURIComponent(position)}&`;
    if (restaurant) url += `restaurant=${encodeURIComponent(restaurant)}&`;
    
    // Remove trailing & if exists
    if (url.endsWith('&')) {
        url = url.slice(0, -1);
    }
    
    window.location.href = url;
    return false;
}
