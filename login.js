const loginForm = document.getElementById("loginForm");
const emailField = document.getElementById("useremail");
const passwordField = document.getElementById("userpassword");
const showPassCheckbox = document.getElementById("showPass");

// Prefill saved email
window.addEventListener("load", () => {
    const savedEmail = localStorage.getItem("savedEmail");
    if (savedEmail) emailField.value = savedEmail;
});

// Show/hide password
showPassCheckbox.addEventListener("change", () => {
    passwordField.type = showPassCheckbox.checked ? "text" : "password";
});

loginForm.addEventListener("submit", function(e) {
    e.preventDefault();

    const email = emailField.value.trim();
    const password = passwordField.value.trim();

    if (!email || !password) {
        alert("Please fill in all fields!");
        return;
    }

    fetch("/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ email, password })
    })
    .then(res => res.json())
    .then(data => {
        // We use alert here temporarily, but remember not to use alerts in production!
        alert(data.message); 
        
        if (data.status === "success") {
            
            // *** CRUCIAL FIX: Store the full 'user' object with username ***
            // This is required for index.html's safety check and for displaying the name.
            localStorage.setItem("user", JSON.stringify({
                 user_id: data.user_id,
                 email: email,
                 username: data.username // <-- NEW: Storing the username from the server
            }));

            // Save email for prefill (existing logic)
            localStorage.setItem("savedEmail", email);
            
            // Redirect after successful login and data storage
            window.location.href = "Index.html";
        }
    })
    .catch(err => console.error(err));
});
