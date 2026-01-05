import Foundation
import Darwin

public enum LibprocError: Error, CustomStringConvertible {
    case listFailed(pid: pid_t, errno: Int32)

    public var description: String {
        switch self {
        case let .listFailed(pid, err):
            return "proc_pidinfo failed for pid \(pid) (errno=\(err))"
        }
    }
}

public struct Libproc {
    public static func openFilePaths(pid: pid_t) throws -> [String] {
        let fds = try listFileDescriptors(pid: pid)
        var paths: [String] = []
        paths.reserveCapacity(fds.count)
        for fdinfo in fds {
            if fdinfo.proc_fdtype != UInt32(PROX_FDTYPE_VNODE) {
                continue
            }
            if let path = vnodePath(pid: pid, fd: fdinfo.proc_fd) {
                paths.append(path)
            }
        }
        var seen = Set<String>()
        var unique: [String] = []
        unique.reserveCapacity(paths.count)
        for path in paths {
            if seen.insert(path).inserted {
                unique.append(path)
            }
        }
        return unique
    }

    public static func openRolloutLogs(pid: pid_t) throws -> [String] {
        let paths = try openFilePaths(pid: pid)
        return paths.filter { path in
            let name = URL(fileURLWithPath: path).lastPathComponent
            return name.hasPrefix("rollout-") && name.hasSuffix(".jsonl")
        }
    }

    private static func listFileDescriptors(pid: pid_t) throws -> [proc_fdinfo] {
        let stride = MemoryLayout<proc_fdinfo>.stride
        var bufferSize = 4096
        let maxBuffer = 1_048_576
        while true {
            let count = max(1, bufferSize / stride)
            var fds = [proc_fdinfo](repeating: proc_fdinfo(), count: count)
            let bytes = fds.withUnsafeMutableBytes { buf in
                proc_pidinfo(pid, PROC_PIDLISTFDS, 0, buf.baseAddress, Int32(buf.count))
            }
            if bytes < 0 {
                throw LibprocError.listFailed(pid: pid, errno: errno)
            }
            if bytes == 0 {
                return []
            }
            if bytes < bufferSize || bufferSize >= maxBuffer {
                let used = min(Int(bytes) / stride, fds.count)
                return Array(fds.prefix(used))
            }
            bufferSize *= 2
        }
    }

    private static func vnodePath(pid: pid_t, fd: Int32) -> String? {
        var info = vnode_fdinfowithpath()
        let size = MemoryLayout<vnode_fdinfowithpath>.size
        let bytes = withUnsafeMutablePointer(to: &info) { ptr in
            proc_pidfdinfo(pid, fd, PROC_PIDFDVNODEPATHINFO, ptr, Int32(size))
        }
        if bytes != size {
            return nil
        }
        let path = withUnsafePointer(to: &info.pvip.vip_path) { ptr -> String in
            ptr.withMemoryRebound(to: CChar.self, capacity: Int(MAXPATHLEN)) {
                String(cString: $0)
            }
        }
        return path.isEmpty ? nil : path
    }
}
