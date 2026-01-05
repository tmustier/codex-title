// swift-tools-version: 6.2
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "LibprocPoc",
    platforms: [
        .macOS(.v10_15),
    ],
    products: [
        // Products define the executables and libraries a package produces, making them visible to other packages.
        .library(
            name: "LibprocPoc",
            targets: ["LibprocPoc"]
        ),
        .executable(
            name: "libproc-poc",
            targets: ["LibprocPocCLI"]
        ),
        .executable(
            name: "codex-title-poc",
            targets: ["CodexTitlePoc"]
        ),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-testing.git", from: "6.2.0"),
    ],
    targets: [
        // Targets are the basic building blocks of a package, defining a module or a test suite.
        // Targets can depend on other targets in this package and products from dependencies.
        .target(
            name: "LibprocPoc"
        ),
        .executableTarget(
            name: "LibprocPocCLI",
            dependencies: ["LibprocPoc"]
        ),
        .executableTarget(
            name: "CodexTitlePoc",
            dependencies: ["LibprocPoc"]
        ),
        .testTarget(
            name: "LibprocPocTests",
            dependencies: [
                "LibprocPoc",
                .product(name: "Testing", package: "swift-testing"),
            ]
        ),
    ]
)
