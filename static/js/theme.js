
(function () {
    const STORAGE_KEY = "ai-study-assistant-theme";

    function getTheme() {
        try {
            return localStorage.getItem(STORAGE_KEY) === "light"
                ? "light"
                : "dark";
        } catch (error) {
            return "dark";
        }
    }

    function applyTheme(theme) {
        const selected = theme === "light" ? "light" : "dark";

        document.documentElement.setAttribute(
            "data-theme",
            selected
        );

        document.documentElement.setAttribute(
            "data-bs-theme",
            selected
        );

        document.querySelectorAll(".theme-toggle").forEach(toggle => {
            toggle.checked = selected === "dark";
        });

        document.querySelectorAll(".theme-mode-label").forEach(label => {
            label.textContent = selected === "dark"
                ? "Dark Mode"
                : "Light Mode";
        });
    }

    // Apply saved preference as soon as the script loads.
    applyTheme(getTheme());

    document.addEventListener("change", function (event) {
        if (!event.target.matches(".theme-toggle")) {
            return;
        }

        const selectedTheme = event.target.checked
            ? "dark"
            : "light";

        try {
            localStorage.setItem(STORAGE_KEY, selectedTheme);
        } catch (error) {
            // Theme still works for the current page.
        }

        applyTheme(selectedTheme);
    });

    document.addEventListener("DOMContentLoaded", function () {
        applyTheme(getTheme());
    });
})();
