import SwiftUI

struct QuestionModeView: View {
    @EnvironmentObject var connection: TTConnectionController
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Image(systemName: connection.handRaised ? "hand.raised.fill" : "hand.raised")
                    .font(.system(size: 72))
                    .foregroundStyle(connection.handRaised ? .orange : .secondary)
                    .accessibilityHidden(true)

                Text(connection.handRaised ? "Hand gehoben" : "Hand nicht gehoben")
                    .font(.title2)
                    .accessibilityAddTraits(.isHeader)

                Button(action: toggleHand) {
                    Text(connection.handRaised ? "Hand senken" : "Hand heben")
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(connection.handRaised ? Color.orange : Color.blue)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .padding(.horizontal)
                .accessibilityLabel(connection.handRaised ? "Hand senken" : "Hand heben")
                .accessibilityHint("Zeigt Moderatoren an, dass du sprechen möchtest")

                Spacer()
            }
            .padding(.top, 40)
            .navigationTitle("Fragezeichen-Modus")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Schließen") { dismiss() }
                }
            }
        }
    }

    private func toggleHand() {
        Task {
            if connection.handRaised {
                await connection.lowerHand()
            } else {
                await connection.raiseHand()
            }
        }
    }
}
