document.addEventListener("DOMContentLoaded", () => {

    const form = document.getElementById("contactForm");
    const whatsappBox = document.getElementById("whatsappBox");
    const whatsappLink = document.getElementById("whatsappLink");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const name = document.getElementById("name").value;
        const phone = document.getElementById("phone").value;
        const message = document.getElementById("message").value;

        const response = await fetch("/contact", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                name: name,
                phone: phone,
                message: message
            })
        });

        const result = await response.json();

        if (result.status === "success") {

            // WhatsApp auto message
            const text = `Hello, my name is ${name}. I submitted a consultation request on your website.

My phone number: ${phone}

My issue: ${message}`;

            const encodedText = encodeURIComponent(text);

            const whatsappNumber = "7900331626"; // ← REAL NUMBER
            const url = `https://wa.me/${whatsappNumber}?text=${encodedText}`;

            whatsappLink.href = url;
            whatsappBox.style.display = "block";

            form.reset();
        } else {
            alert("Something went wrong. Please try again.");
        }
    });

});
