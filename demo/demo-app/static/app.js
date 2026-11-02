// Demo front-end with deliberate review findings.

const user = { id: 7, role: "admin" };
const allowed = user.role === "admin";

document.getElementById("output").innerHTML = location.hash.substring(1);

function render(message) {
  const node = document.getElementById("messages");
  node.outerHTML = message;
}

if (allowed) {
  render("<p>Welcome, administrator</p>");
}
