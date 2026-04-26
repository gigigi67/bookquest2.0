const registerForm = document.getElementById("registerForm");
const usernameField = document.getElementById("username"); // <-- NEW: Get the username field
const emailField = document.getElementById("email");
const passwordField = document.getElementById("password");
const confirmField = document.getElementById("confirmPassword");
const showPassCheckbox = document.getElementById("showPass");

// Show/hide passwords
showPassCheckbox.addEventListener("change", () => {
    const type = showPassCheckbox.checked ? "text" : "password";
    passwordField.type = type;
    confirmField.type = type;
});

registerForm.addEventListener("submit", function(e) {
    e.preventDefault();

    const username = usernameField.value.trim(); // <-- NEW: Get the username value
    const email = emailField.value.trim();
    const password = passwordField.value.trim();
    const confirmPassword = confirmField.value.trim();

    // <-- EDITED: Check for username emptiness
    if (!username || !email || !password || !confirmPassword) {
        alert("Please fill in all fields!");
        return;
    }

    if (password !== confirmPassword) {
        alert("Passwords do not match!");
        return;
    }

    fetch("/register", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        // <-- EDITED: Include username in the request body
        body: JSON.stringify({ username, email, password })
    })
    .then(res => res.json())
    .then(data => {
        alert(data.message);
        if (data.status === "success") {
            // Optionally save email to prefill login
            localStorage.setItem("savedEmail", email);
            
            // Set the full user object expected by index.html after successful registration
            localStorage.setItem("user", JSON.stringify({ 
                 user_id: data.user_id, 
                 email: email,
                 username: data.username 
            }));
            
            window.location.href = "Index.html"; // redirect after registration
        }
    })
    .catch(err => console.error(err));
});
