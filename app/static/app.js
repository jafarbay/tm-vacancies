// Mobile: collapse the filter panel by default (it is open in HTML so it works without JS).
document.addEventListener("DOMContentLoaded", () => {
  const filters = document.getElementById("filters");
  if (filters && matchMedia("(max-width: 880px)").matches) filters.removeAttribute("open");
});
