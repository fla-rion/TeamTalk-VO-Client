import UIKit
import SwiftUI

enum TTAccessibility {
    /// Liest eine Nachricht via VoiceOver vor.
    static func announce(_ message: String, delay: Double = 0) {
        let work = {
            UIAccessibility.post(notification: .announcement, argument: message)
        }
        if delay > 0 {
            DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
        } else {
            DispatchQueue.main.async(execute: work)
        }
    }

    /// Setzt accessibilityLabel und hint auf einem View.
    static func label(_ label: String, hint: String? = nil) -> some View {
        EmptyView()
            .accessibilityLabel(label)
            .accessibilityHint(hint ?? "")
    }
}

extension View {
    func ttAccessible(label: String, hint: String? = nil, isButton: Bool = false) -> some View {
        self
            .accessibilityLabel(label)
            .accessibilityHint(hint ?? "")
            .accessibilityAddTraits(isButton ? .isButton : [])
    }
}
