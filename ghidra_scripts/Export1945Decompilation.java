// Export decompiler output for every function discovered by the R5900-aware analysis.
// This is static pseudocode output, not original source and not a behavioral proof.
// All outputs are written to an external analysis directory, never the project tree.
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

public class Export1945Decompilation extends GhidraScript {
    private static String csv(String value) {
        if (value == null) value = "";
        return "\"" + value.replace("\"", "\"\"").replace("\r", " ").replace("\n", " ") + "\"";
    }

    private static String hex(Address address) {
        return address == null ? "" : String.format("0x%08X", address.getOffset());
    }

    private BufferedWriter writer(File file) throws Exception {
        File parent = file.getAbsoluteFile().getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new Exception("Could not create output directory: " + parent);
        }
        return new BufferedWriter(new OutputStreamWriter(
            new FileOutputStream(file), StandardCharsets.UTF_8));
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1 || args[0].trim().isEmpty()) {
            throw new IllegalArgumentException(
                "Usage: Export1945Decompilation.java <output-directory> [timeout-seconds]");
        }
        if (currentProgram == null) throw new IllegalStateException("No current program was imported");
        if (!currentProgram.getLanguage().getLanguageID().toString().toLowerCase().contains("r5900")) {
            throw new IllegalStateException("Refusing to decompile without an R5900 language: " +
                currentProgram.getLanguage().getLanguageID());
        }
        int timeoutSeconds = 30;
        if (args.length > 1) timeoutSeconds = Integer.parseInt(args[1]);
        if (timeoutSeconds < 1 || timeoutSeconds > 600) {
            throw new IllegalArgumentException("timeout-seconds must be in [1, 600]");
        }

        File outDir = new File(args[0]).getCanonicalFile();
        File sourceDir = new File(outDir, "functions");
        if (!sourceDir.isDirectory() && !sourceDir.mkdirs()) {
            throw new Exception("Could not create decompilation directory: " + sourceDir);
        }
        File manifest = new File(outDir, "ghidra_decompile_manifest.csv");
        long total = 0;
        long completed = 0;
        long failed = 0;
        DecompInterface decompiler = new DecompInterface();
        try {
            if (!decompiler.openProgram(currentProgram)) {
                throw new Exception("DecompInterface could not open the imported R5900 program");
            }
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            try (BufferedWriter out = writer(manifest)) {
                out.write("entry,name,prototype,status,elapsed_ms,output_file,error\n");
                while (functions.hasNext() && !monitor.isCancelled()) {
                    Function function = functions.next();
                    Address entry = function.getEntryPoint();
                    String entryHex = hex(entry);
                    String outputName = entryHex + ".c";
                    String status = "FAILED";
                    String error = "";
                    long started = System.currentTimeMillis();
                    try {
                        DecompileResults result = decompiler.decompileFunction(
                            function, timeoutSeconds, monitor);
                        if (result == null) {
                            error = "decompileFunction returned null";
                        } else if (!result.decompileCompleted()) {
                            error = result.getErrorMessage();
                            status = "INCOMPLETE";
                        } else if (result.getDecompiledFunction() == null ||
                                   result.getDecompiledFunction().getC() == null ||
                                   result.getDecompiledFunction().getC().trim().isEmpty()) {
                            error = "decompiler completed without C output";
                        } else {
                            File outputFile = new File(sourceDir, outputName);
                            try (BufferedWriter code = writer(outputFile)) {
                                code.write("/* Ghidra-generated pseudocode; not original source. */\n");
                                code.write("/* Entry: " + entryHex + " | Name: " +
                                    function.getName(true).replace("*/", "* /") + " */\n");
                                code.write(result.getDecompiledFunction().getC());
                                code.write("\n");
                            }
                            status = "SUCCESS";
                            completed++;
                        }
                    } catch (Exception exception) {
                        error = exception.getClass().getSimpleName() + ": " + exception.getMessage();
                    }
                    long elapsed = System.currentTimeMillis() - started;
                    if (!"SUCCESS".equals(status)) failed++;
                    out.write(entryHex + "," + csv(function.getName(true)) + "," +
                        csv(function.getPrototypeString(false, true)) + "," + status + "," +
                        elapsed + "," + csv("functions/" + outputName) + "," + csv(error) + "\n");
                    total++;
                    if (total % 50 == 0) {
                        println("Decompilation progress: " + total + " functions; success=" +
                            completed + "; incomplete/failed=" + failed);
                    }
                }
            }
            if (monitor.isCancelled()) throw new Exception("Decompilation export cancelled");
        } finally {
            decompiler.dispose();
        }
        println("Decompilation export summary: total=" + total + ", success=" + completed +
            ", incomplete_or_failed=" + failed + ", timeout_seconds=" + timeoutSeconds);
        println("Pseudocode files and per-function status: " + manifest.getAbsolutePath());
        if (total == 0) throw new Exception("No discovered functions were exported; refusing empty success");
    }
}
