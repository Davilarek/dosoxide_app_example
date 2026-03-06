#![no_std]

use dosoxide;

#[unsafe(no_mangle)]
pub extern "Rust" fn user_entry_point() -> ! {
    dosoxide::dos::dos_print(b"Hello from Rust!\r\n");
    loop {}
}
