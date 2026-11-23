import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

/**
 * 独立实现的存档校验器：按客户端 CNOfflineSlotArchive.inspect + readArchive 与
 * CNOfflineProfileReader.read 的规则逐条检查一个 MagiaOfflineSlotArchive/v1 文件。
 *
 * 用法: java tools/VerifyArchive.java <archive.zip>
 * 退出码 0 = 通过，1 = 不通过（打印首个失败原因）。
 *
 * 与 Python 侧 magiasave/zipfmt.py 是两套独立实现，用来交叉验证编辑器输出。
 */
public final class VerifyArchive {
    static final String SCHEMA = "MagiaOfflineSlotArchive/v1";
    static final long MAX_ARCHIVE = 160L * 1024 * 1024, MAX_TOTAL = 128L * 1024 * 1024;
    static final int MAX_ENTRIES = 256, MAX_MANIFEST = 128 * 1024, MAX_PREFERENCES = 16384;
    static final int PART = 512 * 1024, MAX_PARTS = 32;
    static final long STORED = (long) MAX_PARTS * PART;

    static final class Fail extends RuntimeException {
        Fail(String message) { super(message); }
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new Fail(message);
    }

    // ---------------------------------------------------------------- zip

    static final class Record {
        String name; long size, compressed, crc, offset, end, mtime; int flags, method;
    }

    static int u16(byte[] b, long p) { return (b[(int) p] & 0xFF) | ((b[(int) p + 1] & 0xFF) << 8); }

    static long u32(byte[] b, long p) { return (long) u16(b, p) | ((long) u16(b, p + 2) << 16); }

    static void signature(byte[] b, long p, long value) {
        check(u32(b, p) == value, "zip_signature@" + p);
    }

    static boolean nativeFile(String n) {
        return n.matches("start\\.json|send\\.json|replay\\.bin|record\\.json|storyData\\.json|data[0-9]{1,24}\\.bin|entryQuest\\.json");
    }

    static boolean builtin(String p) { return p.equals("new") || p.equals("progress") || p.equals("full"); }

    static boolean allowedNamespace(String preset, String ns) {
        if (!builtin(preset)) return false;
        if (ns == null || ns.length() > 48) return false;
        return ns.equals("off3_selected")
                || ns.matches("off3_(?:bak_)?" + preset + "_(?:head|[ab]_(?:[0-9]|[12][0-9]|3[01]))")
                || ns.equals("off3_diag_" + preset)
                || ns.matches("off3_(?:replay|activity)_" + preset + "(?:_[a-z0-9]{1,10})?");
    }

    static boolean archiveLeaf(String preset, String path) {
        if (path == null) return false;
        if (path.startsWith("state/") && path.endsWith(".json"))
            return allowedNamespace(preset, path.substring(6, path.length() - 5));
        return path.startsWith("native/") && nativeFile(path.substring(7));
    }

    static boolean envelopePath(String path) {
        if (path.equals("manifest.json") || path.equals("preferences.json")) return true;
        return archiveLeaf("new", path) || archiveLeaf("progress", path) || archiveLeaf("full", path);
    }

    static long limit(String path) {
        if (path.equals("manifest.json")) return MAX_MANIFEST;
        if (path.equals("preferences.json")) return MAX_PREFERENCES;
        if (path.startsWith("state/")) return PART;
        if (path.equals("native/entryQuest.json")) return 16384;
        if (path.startsWith("native/")) return 32L * 1024 * 1024;
        throw new Fail("path " + path);
    }

    static long timestampExtra(byte[] b, long p, int bytes) {
        if (bytes == 0) return -1;
        check(bytes == 9 && u16(b, p) == 0x5455 && u16(b, p + 2) == 5 && (b[(int) p + 4] & 0xFF) == 1,
                "zip_extra");
        return u32(b, p + 5);
    }

    static String name(byte[] b, long p, int count) {
        check(count >= 1 && count <= 96, "zip_name");
        for (int i = 0; i < count; i++) {
            int v = b[(int) p + i] & 0xFF;
            check(v >= 32 && v <= 126, "zip_name charset");
        }
        String s = new String(b, (int) p, count, StandardCharsets.US_ASCII);
        check(envelopePath(s), "zip_path " + s);
        return s;
    }

    static SortedMap<String, Record> inspect(byte[] b) {
        long size = b.length;
        check(size >= 22 && size <= MAX_ARCHIVE, "zip_size");
        long end = size - 22;
        signature(b, end, 0x06054b50L);
        check(u16(b, end + 4) == 0 && u16(b, end + 6) == 0, "zip_disk");
        int onDisk = u16(b, end + 8), count = u16(b, end + 10);
        long centralSize = u32(b, end + 12), central = u32(b, end + 16);
        check(u16(b, end + 20) == 0, "zip_comment");
        check(onDisk == count && count >= 2 && count <= MAX_ENTRIES, "zip_directory count");
        check(central + centralSize == size - 22, "zip_directory size");
        long p = central;
        SortedMap<String, Record> records = new TreeMap<>();
        long total = 0;
        for (int i = 0; i < count; i++) {
            check(p + 46 <= end, "zip_directory overflow");
            signature(b, p, 0x02014b50L);
            int needed = u16(b, p + 6);
            Record r = new Record();
            r.flags = u16(b, p + 8);
            r.method = u16(b, p + 10);
            r.crc = u32(b, p + 16);
            r.compressed = u32(b, p + 20);
            r.size = u32(b, p + 24);
            int nameLen = u16(b, p + 28), extra = u16(b, p + 30), comment = u16(b, p + 32);
            int disk = u16(b, p + 34);
            long attrs = u32(b, p + 38);
            r.offset = u32(b, p + 42);
            int mode = (int) (attrs >>> 16) & 0170000;
            check(needed <= 20, "zip_attributes needed");
            check((r.flags & ~0x808) == 0, "zip_attributes flags");
            check(r.method == 0 || r.method == 8, "zip_attributes method");
            check(comment == 0 && disk == 0, "zip_attributes comment/disk");
            check(mode == 0 || mode == 0100000, "zip_attributes mode");
            check((attrs & 16) == 0, "zip_attributes dir");
            check(r.compressed != 0xffffffffL && r.size != 0xffffffffL && r.offset < central, "zip_attributes zip64");
            r.name = name(b, p + 46, nameLen);
            r.mtime = timestampExtra(b, p + 46 + nameLen, extra);
            check(records.put(r.name, r) == null, "duplicate " + r.name);
            check(r.size <= limit(r.name) && r.compressed <= MAX_ARCHIVE, "declared_size " + r.name);
            total += r.size;
            check(total <= MAX_TOTAL, "total_size");
            p += 46 + nameLen + extra + comment;
        }
        check(p == central + centralSize, "zip_directory walk");
        check(records.containsKey("manifest.json") && records.containsKey("preferences.json"), "zip_directory members");
        List<Record> ordered = new ArrayList<>(records.values());
        ordered.sort(Comparator.comparingLong(o -> o.offset));
        long next = 0;
        for (Record r : ordered) {
            check(r.offset == next && r.offset + 30 <= central, "zip_offset");
            p = r.offset;
            signature(b, p, 0x04034b50L);
            check(u16(b, p + 4) <= 20 && u16(b, p + 6) == r.flags && u16(b, p + 8) == r.method, "zip_header");
            long crc = u32(b, p + 14), compressed = u32(b, p + 18), plain = u32(b, p + 22);
            int nameLen = u16(b, p + 26), extra = u16(b, p + 28);
            check(name(b, p + 30, nameLen).equals(r.name), "zip_header name");
            check(timestampExtra(b, p + 30 + nameLen, extra) == r.mtime, "zip_extra_conflict");
            if ((r.flags & 8) == 0) {
                check(crc == r.crc && compressed == r.compressed && plain == r.size, "zip_header sizes");
            } else {
                check((crc == 0 || crc == r.crc) && (compressed == 0 || compressed == r.compressed)
                        && (plain == 0 || plain == r.size), "zip_header sizes (descriptor)");
            }
            next = p + 30 + nameLen + extra + r.compressed;
            check(next <= central, "zip_offset data");
            if ((r.flags & 8) != 0) {
                if (u32(b, next) == 0x08074b50L) next += 4;
                check(u32(b, next) == r.crc && u32(b, next + 4) == r.compressed && u32(b, next + 8) == r.size,
                        "zip_descriptor");
                next += 12;
            }
            r.end = next;
        }
        check(next == central, "zip_gap");
        return records;
    }

    // ---------------------------------------------------------------- JSON

    static final class Json {
        private final String s;
        private int i;
        Json(String s) { this.s = s; }

        static Object parse(String text) {
            Json parser = new Json(text);
            Object value = parser.value();
            parser.ws();
            check(parser.i == text.length(), "json trailing");
            return value;
        }

        void ws() { while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }

        Object value() {
            ws();
            check(i < s.length(), "json eof");
            char c = s.charAt(i);
            if (c == '{') return object();
            if (c == '[') return array();
            if (c == '"') return string();
            if (s.startsWith("true", i)) { i += 4; return Boolean.TRUE; }
            if (s.startsWith("false", i)) { i += 5; return Boolean.FALSE; }
            if (s.startsWith("null", i)) { i += 4; return null; }
            return number();
        }

        Map<String, Object> object() {
            Map<String, Object> out = new LinkedHashMap<>();
            i++;
            ws();
            if (s.charAt(i) == '}') { i++; return out; }
            while (true) {
                ws();
                String key = string();
                ws();
                check(s.charAt(i) == ':', "json colon");
                i++;
                out.put(key, value());
                ws();
                char c = s.charAt(i++);
                if (c == '}') return out;
                check(c == ',', "json object sep");
            }
        }

        List<Object> array() {
            List<Object> out = new ArrayList<>();
            i++;
            ws();
            if (s.charAt(i) == ']') { i++; return out; }
            while (true) {
                out.add(value());
                ws();
                char c = s.charAt(i++);
                if (c == ']') return out;
                check(c == ',', "json array sep");
            }
        }

        String string() {
            check(s.charAt(i) == '"', "json string");
            i++;
            StringBuilder out = new StringBuilder();
            while (true) {
                char c = s.charAt(i++);
                if (c == '"') break;
                if (c == '\\') {
                    char e = s.charAt(i++);
                    switch (e) {
                        case 'n': out.append('\n'); break;
                        case 't': out.append('\t'); break;
                        case 'r': out.append('\r'); break;
                        case 'b': out.append('\b'); break;
                        case 'f': out.append('\f'); break;
                        case 'u':
                            out.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                            i += 4;
                            break;
                        default: out.append(e);
                    }
                } else {
                    out.append(c);
                }
            }
            return out.toString();
        }

        Double number() {
            int start = i;
            while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
            check(i > start, "json number");
            return Double.valueOf(s.substring(start, i));
        }
    }

    // ---------------------------------------------------------------- 校验

    static long integer(Map<String, Object> o, String key, long min, long max) {
        Object v = o.get(key);
        check(v instanceof Number, "integer " + key);
        double d = ((Number) v).doubleValue();
        long n = (long) d;
        check(d == n && n >= min && n <= max, "integer range " + key + "=" + v);
        return n;
    }

    static String string(Map<String, Object> o, String key) {
        Object v = o.get(key);
        check(v instanceof String, "string " + key);
        return (String) v;
    }

    static void keys(Map<String, Object> o, String... names) {
        Set<String> allowed = new HashSet<>(Arrays.asList(names));
        check(o.size() == allowed.size(), "fields size " + o.keySet());
        for (String key : o.keySet()) check(allowed.contains(key), "fields " + key);
    }

    static int utf8(String text) { return text.getBytes(StandardCharsets.UTF_8).length; }

    static String hex(byte[] data) {
        StringBuilder sb = new StringBuilder();
        for (byte value : data) sb.append(String.format("%02x", value & 255));
        return sb.toString();
    }

    static String sha256(byte[] data) throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(data));
    }

    static long date(String s) throws Exception {
        check(s != null && s.matches("[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"), "date format " + s);
        java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.ROOT);
        f.setLenient(false);
        f.setTimeZone(TimeZone.getTimeZone("UTC"));
        java.util.Date d = f.parse(s);
        check(s.equals(f.format(d)), "date strict " + s);
        return d.getTime();
    }

    static final class Profile {
        long revision;
        Map<String, Object> value;
    }

    static Profile readProfile(Map<String, String> state, String template) {
        String prefix = "off3_" + template;
        String headText = state.get(prefix + "_head");
        check(headText != null, "缺少 " + prefix + "_head");
        @SuppressWarnings("unchecked")
        Map<String, Object> head = (Map<String, Object>) Json.parse(headText);
        integer(head, "formatVersion", 1, 1);
        boolean encoded = head.containsKey("encoding");
        if (encoded) {
            String encoding = string(head, "encoding");
            check(encoding.equals("json-shapes-v1")
                    || encoding.equals("json-shapes-v1+gacha-history-details-cleared-v1"), "encoding");
        }
        String bank = string(head, "bank");
        check(bank.equals("a") || bank.equals("b"), "bank");
        long parts = integer(head, "parts", 1, MAX_PARTS);
        long revision = integer(head, "revision", 1, 9007199254740991L);
        long length = integer(head, "bytes", 1, STORED);
        StringBuilder raw = new StringBuilder();
        for (int i = 0; i < parts; i++) {
            String partText = state.get(prefix + "_" + bank + "_" + i);
            check(partText != null, "缺片 " + prefix + "_" + bank + "_" + i);
            check(utf8(partText) <= PART, "part 超过 512KB: " + i + " " + utf8(partText));
            @SuppressWarnings("unchecked")
            Map<String, Object> part = (Map<String, Object>) Json.parse(partText);
            integer(part, "revision", revision, revision);
            integer(part, "part", i, i);
            raw.append(string(part, "data"));
            check(raw.length() <= STORED, "拼接超限");
        }
        check(utf8(raw.toString()) == length, "head.bytes 不匹配: " + utf8(raw.toString()) + " != " + length);
        String value = raw.toString();
        if (encoded) {
            // 编码体只检查信封，解码逻辑由 Python 侧覆盖（本校验器聚焦字节协议）
            @SuppressWarnings("unchecked")
            Map<String, Object> envelope = (Map<String, Object>) Json.parse(value);
            check("MagiaProfileShapes".equals(envelope.get("format")), "shapes format");
            integer(envelope, "version", 1, 1);
            check(envelope.get("shapes") instanceof List && envelope.get("strings") instanceof List, "shapes tables");
        } else {
            @SuppressWarnings("unchecked")
            Map<String, Object> profile = (Map<String, Object>) Json.parse(value);
            integer(profile, "formatVersion", 1, 1);
            check(string(profile, "kind").matches("new|imported-progress|halfway|full-unlock"), "kind");
            check(profile.get("state") instanceof Map, "state");
            String kind = string(profile, "kind");
            String want = template.equals("new") ? "new" : template.equals("progress") ? "imported-progress" : "full-unlock";
            check(kind.equals(want), "模板不匹配: kind=" + kind + " template=" + template);
            Profile out = new Profile();
            out.revision = revision;
            out.value = profile;
            return out;
        }
        Profile out = new Profile();
        out.revision = revision;
        return out;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("用法: java VerifyArchive.java <archive.zip>");
            System.exit(2);
        }
        byte[] blob = Files.readAllBytes(Paths.get(args[0]));
        SortedMap<String, Record> records = inspect(blob);
        Map<String, byte[]> payload = new TreeMap<>();
        try (ZipFile zip = new ZipFile(args[0])) {
            for (String name : records.keySet()) {
                try (InputStream in = zip.getInputStream(zip.getEntry(name))) {
                    ByteArrayOutputStream out = new ByteArrayOutputStream();
                    byte[] buffer = new byte[32768];
                    int n;
                    while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
                    payload.put(name, out.toByteArray());
                }
            }
        }
        check(payload.size() == records.size(), "zip 条目与记录数量不一致");

        @SuppressWarnings("unchecked")
        Map<String, Object> manifest = (Map<String, Object>) Json.parse(new String(payload.get("manifest.json"), StandardCharsets.UTF_8));
        keys(manifest, "schema", "version", "template", "label", "entries");
        check(SCHEMA.equals(manifest.get("schema")), "schema");
        integer(manifest, "version", 1, 1);
        String template = string(manifest, "template");
        check(template.matches("new|progress|full"), "template");
        String label = string(manifest, "label");
        check(!label.trim().isEmpty() && label.length() <= 80, "label");

        @SuppressWarnings("unchecked")
        List<Object> entries = (List<Object>) manifest.get("entries");
        check(entries.size() == records.size() - 1, "manifest 条目数");
        Map<String, long[]> expected = new TreeMap<>();
        for (Object item : entries) {
            @SuppressWarnings("unchecked")
            Map<String, Object> row = (Map<String, Object>) item;
            keys(row, "path", "bytes", "sha256");
            String path = string(row, "path");
            check(path.equals("preferences.json") || archiveLeaf(template, path), "manifest namespace " + path);
            long bytes = integer(row, "bytes", 0, limit(path));
            String sha = string(row, "sha256");
            check(sha.matches("[0-9a-f]{64}"), "manifest sha256 形状");
            check(records.containsKey(path) && records.get(path).size == bytes, "manifest bytes " + path);
            check(!expected.containsKey(path), "manifest 重复 " + path);
            expected.put(path, new long[]{bytes});
            check(sha.equals(sha256(payload.get(path))), "sha256 不匹配 " + path);
        }
        check(expected.containsKey("preferences.json"), "manifest 缺 preferences");

        Map<String, String> state = new TreeMap<>();
        for (Map.Entry<String, byte[]> item : payload.entrySet()) {
            if (item.getKey().startsWith("state/")) {
                state.put(item.getKey().substring(6, item.getKey().length() - 5),
                        new String(item.getValue(), StandardCharsets.UTF_8));
            }
        }
        Profile profile = readProfile(state, template);
        String selected = state.get("off3_selected");
        if (selected != null) {
            @SuppressWarnings("unchecked")
            Map<String, Object> marker = (Map<String, Object>) Json.parse(selected);
            keys(marker, "id");
            check(template.equals(marker.get("id")), "off3_selected.id");
        }
        System.out.println("PASS " + args[0]);
        System.out.println("  entries=" + records.size() + " template=" + template + " label=" + label
                + " revision=" + profile.revision + " profiles=" + (profile.value == null ? "encoded" : "raw"));
        System.out.println("  state namespaces=" + state.size());
    }
}
