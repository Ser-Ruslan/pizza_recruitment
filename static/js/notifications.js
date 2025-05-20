
document.addEventListener('DOMContentLoaded', function() {
    // Обработка клика по кнопке "Отметить как прочитанное"
    document.querySelectorAll('.notification-menu form').forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const notificationId = this.querySelector('button[name="mark_read"]').value;
            const notificationItem = this.closest('.dropdown-item');
            
            fetch(this.action, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': this.querySelector('[name="csrfmiddlewaretoken"]').value
                },
                body: new FormData(this)
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Убираем жирный шрифт
                    notificationItem.classList.remove('fw-bold');
                    // Убираем кнопку
                    this.remove();
                    // Обновляем счетчик
                    const countBadge = document.querySelector('.notification-count');
                    const currentCount = parseInt(countBadge.textContent);
                    if (currentCount > 1) {
                        countBadge.textContent = currentCount - 1;
                    } else {
                        countBadge.remove();
                    }
                }
            });
        });
    });
});

