document.addEventListener("DOMContentLoaded", () => {
  const statusContainer = document.getElementById("print-status");
  const socket = io();

  socket.on("print_status", (data) => {
    const existingStatus = document.getElementById(`status-${data.job_id}`);
    const statusDiv = existingStatus || document.createElement("div");

    if (!existingStatus) {
      statusDiv.id = `status-${data.job_id}`;
      statusDiv.className = "print-status-item";
      statusContainer.prepend(statusDiv);
    }

    let iconClass, statusText;
    switch (data.status) {
      case "uploaded":
        iconClass = "fas fa-upload";
        statusText = "تم رفع الملف";
        statusDiv.className = "print-status-item info";
        break;
      case "printing":
        iconClass = "fas fa-spinner fa-spin";
        statusText = "قيد الطباعة";
        statusDiv.className = "print-status-item info";
        break;
      case "completed":
        iconClass = "fas fa-check-circle";
        statusText = "تمت الطباعة";
        statusDiv.className = "print-status-item success";
        break;
      case "error":
        iconClass = "fas fa-exclamation-circle";
        statusText = `خطأ: ${data.message}`;
        statusDiv.className = "print-status-item error";
        break;
    }

    statusDiv.innerHTML = `
            <i class="${iconClass}"></i>
            <span>${data.filename}: ${statusText}</span>
        `;
  });
});
