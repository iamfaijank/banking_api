(() => {
    console.log("Starting Value Dated TTUM Maker...");


    const ALLOWED_EXTENSIONS = ["xlsx", "xls", "xlsb", "csv", "ods"];

    const FIELD_LAYOUT = {
        foracid: 16,
        tran_crncy_code: 3,
        sol_id: 8,
        part_tran_type: 1,
        tran_amt: 17,
        tran_particular: 30,
        empty_middle_fields: 103,
        value_date: 10,
        gl_date: 10
    };

    const REQUIRED_HEADERS = {
        "account number": "foracid",
        "tran currency code": "tran_crncy_code",
        "sol id": "sol_id",
        "part tran type": "part_tran_type",
        "transaction amount": "tran_amt",
        "transaction particular": "tran_particular",
        "value date": "value_date"
    };


    const fileInput = document.getElementById("excelFile");
    const processBtn = document.getElementById("processBtn");
    const statusBox = document.getElementById("statusBox");

    const fileUploadInfo = document.getElementById("fileUploadInfo");

    if (fileInput && fileUploadInfo) {
        fileInput.addEventListener("change", () => {
            const file = fileInput.files && fileInput.files[0];
            if (file) {
                fileUploadInfo.textContent = file.name;
            } else {
                fileUploadInfo.textContent = "No file chosen";
            }
        });
    }


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

        const extension = getFileExtension(file.name);

        if (!ALLOWED_EXTENSIONS.includes(extension)) {
            throw new Error(
                "Only Excel files are allowed: .xlsx, .xls, .xlsb, .csv, .ods"
            );
        }
    }


    function parseWorkbook(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = function (event) {
                try {
                    const workbook = XLSX.read(event.target.result, {
                        type: "array",
                        cellDates: true
                    });

                    resolve(workbook);
                } catch (error) {
                    reject(error);
                }
            };

            reader.onerror = function () {
                reject(new Error("Unable to read the selected file."));
            };

            reader.readAsArrayBuffer(file);
        });
    }


    function normalizeHeader(value) {
        return String(value || "")
            .trim()
            .replace(/\s+/g, " ")
            .toLowerCase();
    }


    function normalizeForacid(value) {
        let account = String(value ?? "").trim();

        if (!account) {
            return "";
        }

        if (/^\d+\.0+$/.test(account)) {
            account = account.replace(/\.0+$/, "");
        }

        return account;
    }


    // function normalizeExcelDate(value) {
    //     if (value instanceof Date && !Number.isNaN(value.getTime())) {
    //         const day = String(value.getDate()).padStart(2, "0");
    //         const month = String(value.getMonth() + 1).padStart(2, "0");
    //         const year = String(value.getFullYear());

    //         return `${day}${month}${year}`;
    //     }

    //     return String(value || "").trim();
    // }

    function normalizeExcelDate(value) {
        // Case 1: Excel date object (Date instance)
        if (value instanceof Date && !Number.isNaN(value.getTime())) {
            const day = String(value.getDate()).padStart(2, "0");
            const month = String(value.getMonth() + 1).padStart(2, "0");
            const year = String(value.getFullYear());

            return `${day}-${month}-${year}`; // DD-MM-YYYY
        }

        // Case 2: String value from Excel
        const raw = String(value ?? "").trim();

        if (!raw) {
            return "";
        }

        // Accept both '-' and '/' as separators
        const parts = raw.split(/[-/]/);

        if (parts.length !== 3) {
            // If not in expected format, return as-is (validation will catch it later)
            return raw;
        }

        let [dayStr, monthStr, yearStr] = parts;

        // Remove any leading/trailing spaces just in case
        dayStr = String(dayStr).trim();
        monthStr = String(monthStr).trim();
        yearStr = String(yearStr).trim();

        // Pad day and month to 2 digits if they are numeric
        if (/^\d+$/.test(dayStr)) {
            dayStr = dayStr.padStart(2, "0");
        }

        if (/^\d+$/.test(monthStr)) {
            monthStr = monthStr.padStart(2, "0");
        }

        // Final format: DD-MM-YYYY
        return `${dayStr}-${monthStr}-${yearStr}`;
    }

    function padRight(value, length) {
        const finalValue = String(value ?? "");

        if (finalValue.length > length) {
            return finalValue.substring(0, length);
        }

        return finalValue.padEnd(length, " ");
    }


    function formatAmount(value) {
        const cleaned = String(value ?? "")
            .replace(/,/g, "")
            .trim();

        const amount = Number(cleaned);

        if (!Number.isFinite(amount) || amount <= 0) {
            throw new Error(`Invalid Transaction Amount: ${value}`);
        }

        const formatted = amount.toFixed(2);

        if (formatted.length > FIELD_LAYOUT.tran_amt) {
            throw new Error(
                `Transaction Amount exceeds ${FIELD_LAYOUT.tran_amt} characters: ${formatted}`
            );
        }

        return formatted.padStart(FIELD_LAYOUT.tran_amt, " ");
    }


    function getHeaderMap(sheet) {
        const matrix = XLSX.utils.sheet_to_json(sheet, {
            header: 1,
            defval: "",
            raw: true
        });

        if (!matrix.length || !matrix[0].length) {
            throw new Error("The uploaded Excel file is empty.");
        }

        const headerRow = matrix[0];
        const headerMap = {};

        headerRow.forEach((header, index) => {
            const normalized = normalizeHeader(header);

            if (normalized) {
                headerMap[normalized] = index;
            }
        });

        const missingHeaders = Object.keys(REQUIRED_HEADERS).filter(
            (header) => headerMap[header] === undefined
        );

        if (missingHeaders.length) {
            throw new Error(
                `Missing required Excel header(s): ${missingHeaders.join(", ")}`
            );
        }

        return {
            matrix,
            headerMap
        };
    }


    function getCellValue(row, headerMap, headerName) {
        const columnIndex = headerMap[headerName];

        if (columnIndex === undefined) {
            return "";
        }

        return row[columnIndex];
    }


    function extractRows(workbook) {
        const firstSheetName = workbook.SheetNames[0];

        if (!firstSheetName) {
            throw new Error("No sheet found in the uploaded workbook.");
        }

        const sheet = workbook.Sheets[firstSheetName];
        const { matrix, headerMap } = getHeaderMap(sheet);
        const rows = [];

        for (let index = 1; index < matrix.length; index++) {
            const excelRow = matrix[index];

            const isEmptyRow = excelRow.every((cell) => {
                return String(cell ?? "").trim() === "";
            });

            if (isEmptyRow) {
                continue;
            }

            const rowNumber = index + 1;

            const foracid = normalizeForacid(
                getCellValue(excelRow, headerMap, "account number")
            );

            const tranCrncyCode = String(
                getCellValue(excelRow, headerMap, "tran currency code") ?? ""
            ).trim();

            const solId = String(
                getCellValue(excelRow, headerMap, "sol id") ?? ""
            ).trim();

            const partTranType = String(
                getCellValue(excelRow, headerMap, "part tran type") ?? ""
            ).trim();

            const tranAmt = getCellValue(
                excelRow,
                headerMap,
                "transaction amount"
            );

            const tranParticular = String(
                getCellValue(excelRow, headerMap, "transaction particular") ?? ""
            ).trim();

            const valueDate = normalizeExcelDate(
                getCellValue(excelRow, headerMap, "value date")
            );

            if (!foracid) {
                throw new Error(`Missing Account Number in row ${rowNumber}.`);
            }

            if (!/^\d+$/.test(foracid)) {
                throw new Error(
                    `Invalid Account Number in row ${rowNumber}. Only digits are allowed.`
                );
            }

            if (!tranCrncyCode) {
                throw new Error(
                    `Missing Tran Currency Code in row ${rowNumber}.`
                );
            }

            if (tranCrncyCode.length > FIELD_LAYOUT.tran_crncy_code) {
                throw new Error(
                    `Tran Currency Code in row ${rowNumber} exceeds ${FIELD_LAYOUT.tran_crncy_code} characters.`
                );
            }

            if (!solId) {
                throw new Error(`Missing Sol ID in row ${rowNumber}.`);
            }

            if (solId.length > FIELD_LAYOUT.sol_id) {
                throw new Error(
                    `Sol ID in row ${rowNumber} exceeds ${FIELD_LAYOUT.sol_id} characters.`
                );
            }

            if (!partTranType) {
                throw new Error(
                    `Missing Part Tran Type in row ${rowNumber}.`
                );
            }

            if (partTranType.length !== 1) {
                throw new Error(
                    `Part Tran Type in row ${rowNumber} must contain exactly 1 character.`
                );
            }

            if (tranAmt === "" || tranAmt === null || tranAmt === undefined) {
                throw new Error(
                    `Missing Transaction Amount in row ${rowNumber}.`
                );
            }

            if (!tranParticular) {
                throw new Error(
                    `Missing Transaction Particular in row ${rowNumber}.`
                );
            }

            if (!valueDate) {
                throw new Error(`Missing Value Date in row ${rowNumber}.`);
            }

            if (valueDate.length > FIELD_LAYOUT.value_date) {
                throw new Error(
                    `Value Date in row ${rowNumber} exceeds ${FIELD_LAYOUT.value_date} characters.`
                );
            }

            rows.push({
                foracid,
                tran_crncy_code: tranCrncyCode,
                sol_id: solId,
                part_tran_type: partTranType,
                tran_amt: tranAmt,
                tran_particular: tranParticular,
                value_date: valueDate
            });
        }

        if (!rows.length) {
            throw new Error("No data rows found in the uploaded Excel file.");
        }

        return rows;
    }


    function buildTTUMLine(row) {
        const foracid = padRight(
            row.foracid,
            FIELD_LAYOUT.foracid
        );

        const tranCrncyCode = padRight(
            row.tran_crncy_code,
            FIELD_LAYOUT.tran_crncy_code
        );

        const solId = padRight(
            row.sol_id,
            FIELD_LAYOUT.sol_id
        );

        const partTranType = padRight(
            row.part_tran_type,
            FIELD_LAYOUT.part_tran_type
        );

        const tranAmt = formatAmount(row.tran_amt);

        const tranParticular = padRight(
            row.tran_particular,
            FIELD_LAYOUT.tran_particular
        );

        const emptyMiddleFields = " ".repeat(
            FIELD_LAYOUT.empty_middle_fields
        );

        const valueDate = padRight(
            row.value_date,
            FIELD_LAYOUT.value_date
        );

        const glDate = " ".repeat(FIELD_LAYOUT.gl_date);

        const line =
            foracid +
            tranCrncyCode +
            solId +
            partTranType +
            tranAmt +
            tranParticular +
            emptyMiddleFields +
            valueDate +
            glDate;

        const expectedLength = 198;

        if (line.length !== expectedLength) {
            throw new Error(
                `TTUM line length validation failed. Expected ${expectedLength}, received ${line.length}.`
            );
        }

        return line;
    }


    function generateTTUMFiles(rows) {
        const lines = rows.map(buildTTUMLine);

        return [
            {
                filename: `VALUE_DATED_TTUM.txt`,
                content: lines.join("\n"),
                record_count: rows.length
            }
        ];
    }


    function downloadBlob(filename, blob) {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");

        anchor.href = url;
        anchor.download = filename;

        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);

        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }


    async function downloadZipFile(files) {
        if (typeof JSZip === "undefined") {
            throw new Error(
                "JSZip library was not loaded. Please ensure the JSZip CDN is available."
            );
        }

        const zip = new JSZip();
        const folder = zip.folder("value_dated_ttum_files");

        files.forEach((file) => {
            folder.file(file.filename, file.content);
        });

        const timestamp = new Date()
            .toISOString()
            .slice(0, 19)
            .replace(/[:T]/g, "-");

        const zipFilename = `VALUE_DATED_TTUM_${timestamp}.zip`;

        setStatus(`Creating ZIP file with ${files.length} TTUM file(s)...`);

        const zipBlob = await zip.generateAsync({
            type: "blob",
            compression: "DEFLATE",
            compressionOptions: {
                level: 6
            }
        });

        downloadBlob(zipFilename, zipBlob);

        return zipFilename;
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

            const workbook = await parseWorkbook(file);
            const rows = extractRows(workbook);

            setStatus(
                `Excel parsed successfully. Total rows: ${rows.length}. Generating TTUM files...`
            );

            const txtFiles = generateTTUMFiles(rows);
            const zipFilename = await downloadZipFile(txtFiles);

            const summary = txtFiles
                .map((file, index) => {
                    return `File ${index + 1}: ${file.record_count} record(s)`;
                })
                .join("\n");

            setStatus(
                `Success.\nRows processed: ${rows.length}\nFiles generated: ${txtFiles.length}\nDownloaded: ${zipFilename}\n\n${summary}`
            );
        } catch (error) {
            console.error(error);
            setStatus(error.message || "Something went wrong.", true);
        }
    });
})();