import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import GraphCoordinateInput from "@/components/learning/practice/GraphCoordinateInput";

function coordinate(label: string) {
  return screen.getByLabelText(label) as HTMLInputElement;
}

it("reports the serialized graph and holds saving until the points are filled", () => {
  const onChange = vi.fn<(answer: string, error: string) => void>();
  render(<GraphCoordinateInput value="" onChange={onChange} />);

  // A fresh editor cannot be saved: the piece has no points yet.
  expect(onChange.mock.lastCall?.[1]).toContain("Участок 1");

  const points: [string, string][] = [["-4", "0"], ["-2,5", "-2,25"], ["-1", "0"]];
  points.forEach(([x, y], index) => {
    fireEvent.change(coordinate(`Участок 1, точка ${index + 1}, x`), { target: { value: x } });
    fireEvent.change(coordinate(`Участок 1, точка ${index + 1}, y`), { target: { value: y } });
  });
  fireEvent.click(screen.getByRole("button", { name: "Добавить выколотую точку" }));
  fireEvent.change(coordinate("Выколотая точка 1, x"), { target: { value: "-3" } });
  fireEvent.change(coordinate("Выколотая точка 1, y"), { target: { value: "-2" } });
  fireEvent.change(screen.getByLabelText(/Значения параметра/), { target: { value: "-2,25; -2" } });

  const [answer, error] = onChange.mock.lastCall ?? [];
  expect(error).toBe("");
  expect(answer).toBe([
    "График:",
    "1) парабола через (−4; 0), (−2,5; −2,25), (−1; 0)",
    "Выколотые точки: (−3; −2)",
    "Значения параметра: −2,25; −2",
  ].join("\n"));
});

it("opens a stored answer for editing and keeps two point fields for a line", () => {
  const stored = [
    "График:",
    "1) прямая через (−2; 1), (−3; 2), при x < −1",
    "Выколотых точек нет.",
    "Значения параметра: не указаны.",
  ].join("\n");
  const onChange = vi.fn<(answer: string, error: string) => void>();
  render(<GraphCoordinateInput value={stored} onChange={onChange} />);

  expect(coordinate("Участок 1, точка 1, x").value).toBe("−2");
  expect(coordinate("Участок 1, точка 2, y").value).toBe("2");
  expect(screen.queryByLabelText("Участок 1, точка 3, x")).toBeNull();
  expect(onChange.mock.lastCall?.[0]).toBe(stored);
  expect(onChange.mock.lastCall?.[1]).toBe("");
});
