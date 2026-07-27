#!/bin/bash
# Local Vatican Bot Test Runner

echo "🧪 Vatican Bot - Local Test"
echo "=================================="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Build images if needed
echo "📦 Building Docker images (if needed)..."
docker-compose -f docker-compose.server.yml build --quiet

# Start services
echo "🚀 Starting services..."
docker-compose -f docker-compose.server.yml up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 5

# Check service status
echo ""
echo "📊 Service Status:"
docker-compose -f docker-compose.server.yml ps

echo ""
echo "=================================="
echo "🧪 Running Complete Booking Test"
echo "=================================="

# Run the test
docker-compose -f docker-compose.server.yml exec -T backend python /app/test_complete_booking.py

TEST_EXIT_CODE=$?

echo ""
echo "=================================="
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ Tests completed successfully!"
else
    echo "❌ Tests failed with exit code: $TEST_EXIT_CODE"
fi
echo "=================================="

echo ""
echo "📝 Useful commands:"
echo "   View logs:  docker-compose -f docker-compose.server.yml logs -f"
echo "   Stop:       docker-compose -f docker-compose.server.yml down"
echo "   Restart:    docker-compose -f docker-compose.server.yml restart"

exit $TEST_EXIT_CODE
