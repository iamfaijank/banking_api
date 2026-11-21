(() => {
    console.log("Starting Finacle TTUM Maker...");

    const DEFAULT_NARRATION = "Share Fund Debit";
    const ALLOWED_EXTENSIONS = ["xlsx", "xls", "xlsb", "csv", "ods"];

    const fileInput = document.getElementById("excelFile");
    const debitAccountInput = document.getElementById("debitAccount");
    const recordsInput = document.getElementById("recordsPerFile");
    const processBtn = document.getElementById("processBtn");
    const statusBox = document.getElementById("statusBox");

    function setStatus(message, isError = false) {
        if (!statusBox) return;
        statusBox.textContent = message;
        statusBox.style.color = isError ? "#b42318" : "#222";
        statusBox.style.background = isError ? "#fef3f2" : "#f1f5f9";
        statusBox.style.borderColor = isError ? "#fecdca" : "#e5e7eb";
    }

    function getFileExtension(filename) {
        const parts = String(filename || "").split(".");
        return parts.length > 1 ? parts.pop().toLowerCase() : "";
    }

    function validateFile(file) {
        if (!file) {
            throw new Error("Please select an Excel file.");
        }

        const ext = getFileExtension(file.name);
        if (!ALLOWED_EXTENSIONS.includes(ext)) {
            throw new Error("Only Excel files are allowed: .xlsx, .xls, .xlsb, .csv, .ods");
        }
    }

    function validateRecordsPerFile(value) {
        const cleaned = String(value || "").trim();

        if (!/^\d+$/.test(cleaned)) {
            throw new Error("Records per file must be an integer.");
        }

        const parsed = Number(cleaned);

        if (!Number.isInteger(parsed) || parsed < 2) {
            throw new Error("Records per file must be greater than or equal to 2.");
        }

        return parsed;
    }

    function validateDebitAccount(value) {
        const cleaned = String(value || "").replace(/\D/g, "").trim();

        if (!cleaned) {
            throw new Error("Please enter debit account number.");
        }

        if (!/^[0-9]{4,15}$/.test(cleaned)) {
            throw new Error("Debit account number must contain only digits and be between 4 and 15 digits.");
        }

        return cleaned;
    }

    function formatAmount(amount) {
        const num = Number(amount);
        if (Number.isNaN(num)) {
            throw new Error(`Invalid amount found: ${amount}`);
        }
        return num.toFixed(2);
    }

    function truncateNarration(text) {
        const finalText = String(text || DEFAULT_NARRATION).trim() || DEFAULT_NARRATION;
        return finalText.substring(0, 30);
    }

    function buildTTUMLine(accountNumber, solId, drCr, amount, narration) {
        const amountStr = formatAmount(amount);

        let paddingCount = 17 - amountStr.length;
        if (paddingCount < 10) {
            paddingCount = 10;
        }

        const spaceStr = " ".repeat(paddingCount);
        const desc = truncateNarration(narration);

        return `${String(accountNumber).trim()} INR${String(solId).trim()}    ${drCr}${spaceStr}${amountStr}${desc}`;
    }

    function chunkArray(arr, size) {
        const out = [];
        for (let i = 0; i < arr.length; i += size) {
            out.push(arr.slice(i, i + size));
        }
        return out;
    }

    function downloadBlob(filename, blob) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function parseWorkbook(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = function (e) {
                try {
                    const data = e.target.result;
                    const workbook = XLSX.read(data, { type: "array" });
                    resolve(workbook);
                } catch (err) {
                    reject(err);
                }
            };

            reader.onerror = function () {
                reject(new Error("Unable to read the selected file."));
            };

            reader.readAsArrayBuffer(file);
        });
    }

    function extractRows(workbook) {
        const firstSheetName = workbook.SheetNames[0];
        if (!firstSheetName) {
            throw new Error("No sheet found in the uploaded workbook.");
        }

        const sheet = workbook.Sheets[firstSheetName];
        const rows = XLSX.utils.sheet_to_json(sheet, {
            defval: "",
            raw: false
        });

        if (!rows.length) {
            throw new Error("The uploaded Excel file is empty.");
        }

        const parsedRows = rows.map((row, index) => {
            const accountNumber = row["Account Number"];
            const solId = row["Sol ID"];
            const amount = row["Amount"];
            const narration = row["Narration"];

            if (!accountNumber) {
                throw new Error(`Missing Account Number in row ${index + 2}.`);
            }

            if (!solId) {
                throw new Error(`Missing Sol ID in row ${index + 2}.`);
            }

            if (amount === "" || amount === null || amount === undefined) {
                throw new Error(`Missing Amount in row ${index + 2}.`);
            }

            const accountStr = String(accountNumber).trim();
            const solIdStr = String(solId).trim();
            const numericAmount = Number(String(amount).replace(/,/g, "").trim());

            if (!/^\d+$/.test(accountStr)) {
                throw new Error(`Invalid Account Number in row ${index + 2}. Only digits allowed.`);
            }

            if (!/^\d+$/.test(solIdStr)) {
                throw new Error(`Invalid Sol ID in row ${index + 2}. Only digits allowed.`);
            }

            if (Number.isNaN(numericAmount) || numericAmount <= 0) {
                throw new Error(`Invalid Amount in row ${index + 2}.`);
            }

            return {
                account_number: accountStr,
                sol_id: solIdStr,
                amount: numericAmount,
                narration: String(narration || "").trim() || DEFAULT_NARRATION
            };
        });

        return parsedRows;
    }

    function generateTTUMFiles(rows, recordsPerFile, debitAccountNumber) {
        const creditPerFile = recordsPerFile - 1;

        if (creditPerFile < 1) {
            throw new Error("Records per file must allow at least 1 credit row and 1 debit row.");
        }

        const chunks = chunkArray(rows, creditPerFile);
        const outputs = [];
        const debitSolId = debitAccountNumber.slice(0, 4);

        chunks.forEach((chunk, index) => {
            const lines = [];
            let totalCredit = 0;

            chunk.forEach((row) => {
                totalCredit += row.amount;

                lines.push(
                    buildTTUMLine(
                        row.account_number,
                        row.sol_id,
                        "C",
                        row.amount,
                        row.narration
                    )
                );
            });

            lines.push(
                buildTTUMLine(
                    debitAccountNumber,
                    debitSolId,
                    "D",
                    totalCredit,
                    DEFAULT_NARRATION
                )
            );

            outputs.push({
                filename: `TTUM_${index + 1}.txt`,
                content: lines.join("\n"),
                credit_count: chunk.length,
                total_amount: totalCredit.toFixed(2),
                debit_sol_id: debitSolId
            });
        });

        return outputs;
    }

    async function downloadZipFile(files, debitAccountNumber) {
        if (typeof JSZip === "undefined") {
            throw new Error("JSZip library not loaded. Please include JSZip CDN in HTML.");
        }

        const zip = new JSZip();
        const folder = zip.folder("ttum_files");

        files.forEach((fileObj) => {
            folder.file(fileObj.filename, fileObj.content);
        });

        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
        const zipFilename = `TTUM_${debitAccountNumber}_${timestamp}.zip`;

        setStatus(`Creating ZIP file with ${files.length} TTUM files...`);

        const zipBlob = await zip.generateAsync({
            type: "blob",
            compression: "DEFLATE",
            compressionOptions: { level: 6 }
        });

        downloadBlob(zipFilename, zipBlob);
        return zipFilename;
    }

    if (debitAccountInput) {
        debitAccountInput.addEventListener("input", function () {
            this.value = this.value.replace(/\D/g, "").slice(0, 15);
            this.setCustomValidity("");
        });

        debitAccountInput.addEventListener("blur", function () {
            const val = this.value.trim();
            if (val && !/^[0-9]{4,15}$/.test(val)) {
                this.setCustomValidity("Debit account number must be 4 to 15 digits only.");
            } else {
                this.setCustomValidity("");
            }
        });
    }

    if (recordsInput) {
        recordsInput.addEventListener("input", function () {
            this.value = this.value.replace(/\D/g, "");
        });
    }

    if (!processBtn) {
        console.error("Process button not found.");
        return;
    }

    processBtn.addEventListener("click", async () => {
        try {
            setStatus("Processing...");

            const file = fileInput ? fileInput.files[0] : null;
            validateFile(file);

            const debitAccountNumber = validateDebitAccount(
                debitAccountInput ? debitAccountInput.value : ""
            );

            const recordsPerFile = validateRecordsPerFile(
                recordsInput ? recordsInput.value : ""
            );

            const workbook = await parseWorkbook(file);
            const rows = extractRows(workbook);

            setStatus(`Excel parsed successfully. Total rows: ${rows.length}. Generating TTUM files...`);

            const txtFiles = generateTTUMFiles(rows, recordsPerFile, debitAccountNumber);

            const zipFilename = await downloadZipFile(txtFiles, debitAccountNumber);

            const summary = txtFiles.map((f, i) => {
                return `File ${i + 1}: ${f.credit_count} credit + 1 debit, debit amount ${f.total_amount}, Debit Sol ID ${f.debit_sol_id}`;
            }).join("\n");

            setStatus(
                `Success.\nDebit account: ${debitAccountNumber}\nDebit Sol ID: ${debitAccountNumber.slice(0, 4)}\nRows processed: ${rows.length}\nFiles generated: ${txtFiles.length}\nDownloaded: ${zipFilename}\n\n${summary}`
            );
        } catch (err) {
            console.error(err);
            setStatus(err.message || "Something went wrong.", true);
        }
    });
})();