// Export conservative, reproducible metadata from a Ghidra-analyzed PS2 ELF.
// This script does not execute the input binary or modify original game assets.
// Intended processor: r5900:LE:32:default (Emotion Engine: Reloaded extension).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.program.model.symbol.RefType;
import ghidra.program.model.symbol.SourceType;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

public class Export1945Evidence extends GhidraScript {
    private static final long[][] WINDOWS = new long[][] {
        { 0x00100000L, 0x00100200L },
        { 0x001BDF38L, 0x001BE038L },
        { 0x001B5D60L, 0x001B5E60L },
        { 0x00184E08L, 0x00184F08L },
        { 0x001BE320L, 0x001BE420L },
        { 0x001BE808L, 0x001BE908L },
        { 0x001B5700L, 0x001B5800L }
    };

    private static String csv(String value) {
        if (value == null) value = "";
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }

    private static String hex(Address address) {
        return address == null ? "" : String.format("0x%08X", address.getOffset());
    }

    private static String bytesHex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) result.append(String.format("%02X", value & 0xff));
        return result.toString();
    }

    private BufferedWriter writer(File file) throws Exception {
        File parent = file.getAbsoluteFile().getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new Exception("Could not create output directory: " + parent);
        }
        return new BufferedWriter(new OutputStreamWriter(
            new FileOutputStream(file), StandardCharsets.UTF_8));
    }

    private void exportMetadata(File outDir) throws Exception {
        try (BufferedWriter out = writer(new File(outDir, "ghidra_metadata.txt"))) {
            out.write("program_name=" + currentProgram.getName() + "\n");
            out.write("language_id=" + currentProgram.getLanguage().getLanguageID() + "\n");
            out.write("compiler_spec_id=" + currentProgram.getCompilerSpec().getCompilerSpecID() + "\n");
            out.write("image_base=" + hex(currentProgram.getImageBase()) + "\n");
            out.write("minimum_address=" + hex(currentProgram.getMinAddress()) + "\n");
            out.write("maximum_address=" + hex(currentProgram.getMaxAddress()) + "\n");
            String expectedEntry = getScriptArgs().length > 1 ? getScriptArgs()[1] : "0x00100008";
            out.write("expected_elf_entry=" + expectedEntry + "\n");
            Address expectedAddress = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(
                Long.decode(expectedEntry).longValue());
            Instruction entryInstruction = currentProgram.getListing().getInstructionAt(expectedAddress);
            out.write("expected_entry_instruction_present=" + (entryInstruction != null) + "\n");
            out.write("expected_entry_instruction=" + (entryInstruction == null ? "" : entryInstruction.toString()) + "\n");
            out.write("note=expected_elf_entry is read from the verified ELF-header metadata; decoded instruction presence is independently reported\n");
        }
    }

    private void exportFunctions(File outDir) throws Exception {
        FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
        long count = 0;
        try (BufferedWriter out = writer(new File(outDir, "ghidra_functions.csv"))) {
            out.write("entry,name,prototype,body_min,body_max,body_address_count,thunk\n");
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function function = functions.next();
                AddressSetView body = function.getBody();
                out.write(hex(function.getEntryPoint()) + "," + csv(function.getName(true)) + "," +
                    csv(function.getPrototypeString(false, true)) + "," +
                    hex(body.getMinAddress()) + "," + hex(body.getMaxAddress()) + "," +
                    body.getNumAddresses() + "," + function.isThunk() + "\n");
                count++;
            }
        }
        if (monitor.isCancelled()) throw new Exception("Export cancelled while writing function inventory");
        println("Exported function records: " + count);
    }

    private void exportCallReferences(File outDir) throws Exception {
        ReferenceManager refs = currentProgram.getReferenceManager();
        InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
        Set<String> seen = new HashSet<String>();
        long count = 0;
        try (BufferedWriter out = writer(new File(outDir, "ghidra_call_references.csv"))) {
            out.write("from_address,to_address,reference_type,source_type,source_function,instruction\n");
            while (instructions.hasNext() && !monitor.isCancelled()) {
                Instruction instruction = instructions.next();
                Reference[] from = refs.getReferencesFrom(instruction.getAddress());
                for (Reference reference : from) {
                    RefType type = reference.getReferenceType();
                    if (!(type.isCall() || type.isJump())) continue;
                    String key = instruction.getAddress() + "|" + reference.getToAddress() + "|" + type;
                    if (!seen.add(key)) continue;
                    Function source = currentProgram.getFunctionManager().getFunctionContaining(instruction.getAddress());
                    SourceType sourceType = reference.getSource();
                    out.write(hex(instruction.getAddress()) + "," + hex(reference.getToAddress()) + "," +
                        csv(type.getName()) + "," + csv(sourceType == null ? "" : sourceType.toString()) + "," +
                        csv(source == null ? "" : source.getName(true)) + "," +
                        csv(instruction.toString()) + "\n");
                    count++;
                }
            }
        }
        if (monitor.isCancelled()) throw new Exception("Export cancelled while writing call/jump references");
        println("Exported call/jump reference records: " + count);
    }

    private void exportSelectedListing(File outDir) throws Exception {
        AddressSet addresses = new AddressSet();
        for (long[] window : WINDOWS) {
            Address start = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(window[0]);
            Address end = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(window[1] - 1);
            addresses.addRange(start, end);
        }
        long count = 0;
        try (BufferedWriter out = writer(new File(outDir, "ghidra_selected_disassembly.csv"))) {
            out.write("address,bytes,mnemonic,operands,flow_type,flow_targets\n");
            InstructionIterator instructions = currentProgram.getListing().getInstructions(addresses, true);
            while (instructions.hasNext() && !monitor.isCancelled()) {
                Instruction instruction = instructions.next();
                byte[] bytes = new byte[instruction.getLength()];
                currentProgram.getMemory().getBytes(instruction.getAddress(), bytes);
                StringBuilder operands = new StringBuilder();
                for (int index = 0; index < instruction.getNumOperands(); index++) {
                    if (index > 0) operands.append("; ");
                    operands.append(instruction.getDefaultOperandRepresentation(index));
                }
                StringBuilder targets = new StringBuilder();
                for (Address target : instruction.getFlows()) {
                    if (targets.length() > 0) targets.append(";");
                    targets.append(hex(target));
                }
                out.write(hex(instruction.getAddress()) + "," + csv(bytesHex(bytes)) + "," +
                    csv(instruction.getMnemonicString()) + "," + csv(operands.toString()) + "," +
                    csv(instruction.getFlowType().getName()) + "," + csv(targets.toString()) + "\n");
                count++;
            }
        }
        if (monitor.isCancelled()) throw new Exception("Export cancelled while writing selected disassembly");
        println("Exported selected disassembly instructions: " + count);
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1 || args[0].trim().isEmpty()) {
            throw new IllegalArgumentException("Usage: Export1945Evidence.java <output-directory> [expected-elf-entry]");
        }
        if (currentProgram == null) throw new IllegalStateException("No current program was imported");
        if (!currentProgram.getLanguage().getLanguageID().toString().toLowerCase().contains("r5900")) {
            throw new IllegalStateException("Refusing to export: expected an R5900 language, found " +
                currentProgram.getLanguage().getLanguageID());
        }
        File outDir = new File(args[0]).getCanonicalFile();
        if (!outDir.isDirectory() && !outDir.mkdirs()) {
            throw new Exception("Could not create output directory: " + outDir);
        }
        exportMetadata(outDir);
        exportFunctions(outDir);
        exportCallReferences(outDir);
        exportSelectedListing(outDir);
        println("Evidence exports written to: " + outDir);
    }
}
