"use strict";

const loginForm = document.getElementById("panel-login");
const registerForm = document.getElementById("panel-register");
const tabLogin = document.getElementById("tab-login");
const tabRegister = document.getElementById("tab-register");

function showTab(which) {
  const isLogin = which === "login";
  loginForm.classList.toggle("hidden", !isLogin);
  registerForm.classList.toggle("hidden", isLogin);
  tabLogin.setAttribute("aria-selected", String(isLogin));
  tabRegister.setAttribute("aria-selected", String(!isLogin));
}
tabLogin.addEventListener("click", () => showTab("login"));
tabRegister.addEventListener("click", () => showTab("register"));

document.querySelectorAll("[data-demo]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const [email, password] = btn.dataset.demo.split("|");
    showTab("login");
    document.getElementById("login-email").value = email;
    document.getElementById("login-password").value = password;
    document.getElementById("login-error").textContent = "";
    loginForm.querySelector("button[type=submit]").focus();
  });
});

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("login-error");
  const button = loginForm.querySelector("button[type=submit]");
  error.textContent = "";
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  if (!email || !password) { error.textContent = "Enter your email and password."; return; }
  setBusy(button, true, "Signing in...");
  try {
    const res = await api.post("/api/auth/login", { email, password });
    window.location.href = res.redirect;
  } catch (err) {
    error.textContent = err.message;
    setBusy(button, false);
  }
});

registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const error = document.getElementById("register-error");
  const button = registerForm.querySelector("button[type=submit]");
  error.textContent = "";
  const payload = {
    name: document.getElementById("reg-name").value,
    email: document.getElementById("reg-email").value,
    unit: document.getElementById("reg-unit").value,
    phone: document.getElementById("reg-phone").value,
    password: document.getElementById("reg-password").value,
  };
  setBusy(button, true, "Creating account...");
  try {
    const res = await api.post("/api/auth/register", payload);
    window.location.href = res.redirect;
  } catch (err) {
    error.textContent = err.message;
    setBusy(button, false);
  }
});
