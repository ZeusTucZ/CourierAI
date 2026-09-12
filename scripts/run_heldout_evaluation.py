"""Main baseline is FirstNearby; Smart is loaded from its existing freeze."""
from scripts.compare_nearby_baseline import main

if __name__ == '__main__':
    main(mode_override='heldout')
