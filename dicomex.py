import os
import time
import pydicom
import shutil
import tempfile
import logging
from pynetdicom import AE, debug_logger, VerificationPresentationContexts
from pynetdicom.sop_class import (
    ComputedRadiographyImageStorage,
    DigitalXRayImageStorageForPresentation,
    DigitalXRayImageStorageForProcessing,
    DigitalMammographyXRayImageStorageForPresentation,
    DigitalMammographyXRayImageStorageForProcessing,
    DigitalIntraOralXRayImageStorageForPresentation,
    DigitalIntraOralXRayImageStorageForProcessing,
    CTImageStorage,
    EnhancedCTImageStorage,
    LegacyConvertedEnhancedCTImageStorage,
    Verification
)
import tkinter as tk
from tkinter import filedialog, scrolledtext

# Enable logging
debug_logger()

# Manually defined presentation contexts with SOP class UIDs
custom_presentation_contexts = [
    ('1.2.840.10008.5.1.4.1.1.1', 'Computed Radiography Image Storage'),
    ('1.2.840.10008.5.1.4.1.1.1.1', 'Digital X-Ray Image Storage - For Presentation'),
    ('1.2.840.10008.5.1.4.1.1.1.1.1', 'Digital X-Ray Image Storage - For Processing'),
    ('1.2.840.10008.5.1.4.1.1.2', 'CT Image Storage'),
    ('1.2.840.10008.5.1.4.1.1.2.1', 'Enhanced CT Image Storage'),
    ('1.2.840.10008.5.1.4.1.1.2.2', 'Legacy Converted Enhanced CT Image Storage'),
    ('1.2.840.10008.5.1.4.1.1.1.2', 'Digital Mammography X-Ray Image Storage - For Presentation'),
    ('1.2.840.10008.5.1.4.1.1.1.2.1', 'Digital Mammography X-Ray Image Storage - For Processing'),
    ('1.2.840.10008.5.1.4.1.1.1.3', 'Digital Intra-Oral X-Ray Image Storage - For Presentation'),
    ('1.2.840.10008.5.1.4.1.1.1.3.1', 'Digital Intra-Oral X-Ray Image Storage - For Processing')
]


class DICOMUploader:
    def __init__(self, root):
        self.root = root
        self.root.title("DICOM Uploader")

        self.server_ip = tk.StringVar()
        self.server_port = tk.IntVar()
        self.server_ae_title = tk.StringVar()
        self.sender_ae_title = tk.StringVar()
        self.folder_path = tk.StringVar()
        self.sent_files = set()
        self.record_file = "sent_files.txt"
        self.starting_files = set()

        self.create_widgets()
        self.setup_logging()
        self.load_sent_files()

    def create_widgets(self):
        tk.Label(self.root, text="Server IP:").grid(row=0, column=0, padx=10, pady=10)
        tk.Entry(self.root, textvariable=self.server_ip, width=50).grid(row=0, column=1, padx=10, pady=10)

        tk.Label(self.root, text="Server Port:").grid(row=1, column=0, padx=10, pady=10)
        tk.Entry(self.root, textvariable=self.server_port, width=50).grid(row=1, column=1, padx=10, pady=10)

        tk.Label(self.root, text="Server AE Title:").grid(row=2, column=0, padx=10, pady=10)
        tk.Entry(self.root, textvariable=self.server_ae_title, width=50).grid(row=2, column=1, padx=10, pady=10)

        tk.Label(self.root, text="Sender AE Title:").grid(row=3, column=0, padx=10, pady=10)
        tk.Entry(self.root, textvariable=self.sender_ae_title, width=50).grid(row=3, column=1, padx=10, pady=10)

        tk.Label(self.root, text="Folder Path:").grid(row=4, column=0, padx=10, pady=10)
        tk.Entry(self.root, textvariable=self.folder_path, width=50).grid(row=4, column=1, padx=10, pady=10)
        tk.Button(self.root, text="Browse", command=self.browse_folder).grid(row=4, column=2, padx=10, pady=10)

        tk.Button(self.root, text="Start", command=self.start_monitoring).grid(row=5, column=0, columnspan=3, pady=10)
        tk.Button(self.root, text="Echo Test", command=self.echo_test).grid(row=5, column=1, columnspan=3, pady=10)

        self.status_label = tk.Label(self.root, text="", fg="green")
        self.status_label.grid(row=6, column=0, columnspan=3, padx=10, pady=10)

        self.log_output = scrolledtext.ScrolledText(self.root, width=80, height=20)
        self.log_output.grid(row=7, column=0, columnspan=3, padx=10, pady=10)

    def setup_logging(self):
        self.logger = logging.getLogger("DICOMUploader")
        self.logger.setLevel(logging.DEBUG)

        file_handler = logging.FileHandler("dicom_uploader.log")
        file_handler.setLevel(logging.DEBUG)

        log_handler = self.LogHandler(self.log_output)
        log_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        log_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(log_handler)

    class LogHandler(logging.Handler):
        def __init__(self, widget):
            super().__init__()
            self.widget = widget

        def emit(self, record):
            msg = self.format(record)
            self.widget.insert(tk.END, msg + '\n')
            self.widget.see(tk.END)

    def load_sent_files(self):
        if os.path.exists(self.record_file):
            with open(self.record_file, 'r') as file:
                self.sent_files = set(file.read().splitlines())

    def save_sent_file(self, file_path):
        self.sent_files.add(file_path)
        with open(self.record_file, 'a') as file:
            file.write(file_path + '\n')

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.folder_path.set(folder_selected)

    def start_monitoring(self):
        folder = self.folder_path.get()
        server_ip = self.server_ip.get()
        server_port = self.server_port.get()
        server_ae_title = self.server_ae_title.get()
        sender_ae_title = self.sender_ae_title.get()
        if not folder or not server_ip or not server_port or not server_ae_title or not sender_ae_title:
            self.logger.error("Folder path, server IP, server port, server AE Title, or sender AE Title is missing")
            return

        # Capture the list of files present in the folder at the start
        self.starting_files = set(
            os.path.join(root, f) for root, _, files in os.walk(folder) for f in files if f.endswith('.dcm'))

        self.logger.info(f"Monitoring folder: {folder}")
        self.logger.info(f"Sending files to: {server_ip}:{server_port} (AE Title: {server_ae_title})")

        try:
            while True:
                for root, _, files in os.walk(folder):
                    dicom_files = [os.path.join(root, f) for f in files if f.endswith('.dcm')]
                    for dicom_file in dicom_files:
                        if dicom_file not in self.sent_files and dicom_file not in self.starting_files:
                            self.upload_file(dicom_file, server_ip, server_port, server_ae_title, sender_ae_title)
                time.sleep(10)
        except KeyboardInterrupt:
            self.logger.info("Monitoring stopped")

    def upload_file(self, file_path, server_ip, server_port, server_ae_title, sender_ae_title):
        # Create a temporary copy of the DICOM file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            shutil.copy2(file_path, temp_file.name)
            temp_file_path = temp_file.name

        ds = pydicom.dcmread(temp_file_path)

        ae = AE(ae_title=sender_ae_title)
        for sop_class, _ in custom_presentation_contexts:
            ae.add_requested_context(sop_class)

        assoc = ae.associate(server_ip, server_port, ae_title=server_ae_title)
        if assoc.is_established:
            status = assoc.send_c_store(ds)
            if status:
                self.logger.info(f"Uploaded {file_path} with status: 0x{status.Status:04x}")
                self.status_label.config(text=f"Uploaded {file_path}", fg="green")
                self.save_sent_file(file_path)
            else:
                self.logger.error(f"Failed to upload {file_path}")
                self.status_label.config(text=f"Failed to upload {file_path}", fg="red")
            assoc.release()
        else:
            self.logger.error(f"Association with {server_ip}:{server_port} failed")
            self.status_label.config(text="Association failed", fg="red")

        # Delete the temporary file
        os.remove(temp_file_path)

    def echo_test(self):
        server_ip = self.server_ip.get()
        server_port = self.server_port.get()
        server_ae_title = self.server_ae_title.get()
        sender_ae_title = self.sender_ae_title.get()
        if not server_ip or not server_port or not server_ae_title or not sender_ae_title:
            self.logger.error("Server IP, server port, server AE Title, or sender AE Title is missing")
            return
        self.logger.info(f"Performing echo test to: {server_ip}:{server_port} (AE Title: {server_ae_title})")

        ae = AE(ae_title=sender_ae_title)
        ae.add_requested_context(Verification)

        assoc = ae.associate(server_ip, server_port, ae_title=server_ae_title)
        if assoc.is_established:
            status = assoc.send_c_echo()
            if status:
                self.logger.info("Echo test successful")
                self.status_label.config(text="Echo test successful", fg="green")
            else:
                self.logger.error("Echo test failed")
                self.status_label.config(text="Echo test failed", fg="red")
            assoc.release()
        else:
            self.logger.error(f"Association with {server_ip}:{server_port} failed")
            self.status_label.config(text="Association failed", fg="red")


if __name__ == "__main__":
    root = tk.Tk()
    app = DICOMUploader(root)
    root.mainloop()
