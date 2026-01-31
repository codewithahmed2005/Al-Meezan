document.addEventListener("DOMContentLoaded", () => {
    console.log("JS CONNECTED");

    const form = document.getElementById("contactForm");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const data = {
            name: document.getElementById("name").value,
            phone: document.getElementById("phone").value,
            message: document.getElementById("message").value
        };

        const response = await fetch("/contact", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();
        alert(result.message);
    });
});
