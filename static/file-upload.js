document.addEventListener("DOMContentLoaded", () => {
  const dropArea = document.querySelector(".file-drop-area");
  const fileInput = document.getElementById("files");
  const fileNameDisplay = document.getElementById("file-name");

  ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
    dropArea.addEventListener(eventName, preventDefaults, false);
  });

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  ["dragenter", "dragover"].forEach((eventName) => {
    dropArea.addEventListener(
      eventName,
      () => {
        dropArea.classList.add("highlight");
      },
      false
    );
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropArea.addEventListener(
      eventName,
      () => {
        dropArea.classList.remove("highlight");
      },
      false
    );
  });

  dropArea.addEventListener(
    "drop",
    (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      fileInput.files = files;
      updateFileName(files);
    },
    false
  );

  fileInput.addEventListener("change", () => {
    updateFileName(fileInput.files);
  });

  function updateFileName(files) {
    if (files.length === 0) {
      fileNameDisplay.textContent = "";
      return;
    }
    const names = Array.from(files)
      .map((file) => file.name)
      .join(", ");
    fileNameDisplay.textContent = `الملفات المختارة: ${names}`;
    if (
      files.length > 0 &&
      Array.from(files).some(
        (file) => !file.name.toLowerCase().endswith(".pdf")
      )
    ) {
      fileNameDisplay.classList.add("file-error");
      fileNameDisplay.textContent += " (يرجى اختيار ملفات PDF فقط)";
    } else {
      fileNameDisplay.classList.remove("file-error");
    }
  }
});
