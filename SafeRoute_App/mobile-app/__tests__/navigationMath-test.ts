import { distanceMeters, projectOnRoute } from "../src/lib/navigationMath";

describe("navigation map matching", () => {
  const route: [number, number][] = [[-87.63, 41.88], [-87.62, 41.88], [-87.61, 41.88]];

  it("projects a reliable sample onto the route and computes progress", () => {
    const projection = projectOnRoute([-87.625, 41.88005], route);
    expect(projection).not.toBeNull();
    expect(projection!.distanceFromRouteM).toBeLessThan(10);
    expect(projection!.distanceAlongM).toBeGreaterThan(300);
    expect(projection!.remainingM).toBeGreaterThan(1000);
  });

  it("distinguishes an off-route point from GPS-scale noise", () => {
    const nearby = projectOnRoute([-87.625, 41.8801], route)!;
    const away = projectOnRoute([-87.625, 41.881], route)!;
    expect(nearby.distanceFromRouteM).toBeLessThan(35);
    expect(away.distanceFromRouteM).toBeGreaterThan(35);
  });

  it("uses metric distance with stable zero behavior", () => {
    expect(distanceMeters(route[0], route[0])).toBe(0);
    expect(distanceMeters(route[0], route[1])).toBeGreaterThan(800);
  });
});
