
document.addEventListener("DOMContentLoaded", function () {

    const toggleButtons = document.querySelectorAll(
        ".auth-password-toggle"
    );

    toggleButtons.forEach(function (button) {

        button.addEventListener("click", function () {

            const inputId = button.getAttribute("aria-controls");
            const passwordInput = document.getElementById(inputId);

            if (!passwordInput) return;

            const isHidden = passwordInput.type === "password";

            passwordInput.type = isHidden ? "text" : "password";

            button.setAttribute(
                "aria-label",
                isHidden ? "Hide password" : "Show password"
            );

            button.setAttribute(
                "aria-pressed",
                String(isHidden)
            );

            const icon = button.querySelector("i");

            if (icon) {
                icon.className = isHidden
                    ? "bi bi-eye-slash"
                    : "bi bi-eye";
            }

        });

    });

});
